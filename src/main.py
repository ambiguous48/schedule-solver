from typing import Dict, Tuple

from ortools.sat.python import cp_model as Model
from math import ceil
import plotly.figure_factory as ff
from datetime import datetime, timedelta
import numpy as np

BigM = 10000
#########
D = 4
C_m = [900, 800, 700, 100, 20]
Products_data: list[list[tuple[int, int]]] = [  # product = (machine_id, processing_time).
    [(4, 1), (0, 4), (1, 4), (2, 4), (3, 1)],  # P1
    [(0, 4), (4, 1)],  # P2
    [(4, 1), (0, 4), (4, 1)],  # P3
    [(4, 5)],  # P4
    [(4, 4)],  # P5
]
Products_output = [  # (quantity, number of days).
    (4, 1), (4, 1), (2, 1), (3, 4), (3, 4)]
I_hr = 16
C_ov = 0.25
UB_machines = [4, 4, 4, 4, 4]
No_p = len(Products_data)
p_day = [ceil(Products_output[i][0] / Products_output[i][1])
         for i in range(len(Products_output))]


##########
class Job:
    def __init__(self, product, fproduct, machine_type, duration, last):
        self.product = product
        self.fproduct = fproduct
        self.machine_type = machine_type
        self.duration = duration
        self.last = last


class Machine:
    def __init__(self, type, ftype, cost):
        self.type = type
        self.ftype = ftype
        self.cost = cost


All_Jobs: list[Job] = []
All_Machines: list[Machine] = []
for m in range(len(C_m)):
    for n in range(UB_machines[m]):
        All_Machines.append(Machine(m, n, C_m[m]))

for p in range(len(Products_data)):
    for f in range(p_day[p]):
        for j in range(len(Products_data[p])):
            job = Products_data[p][j]
            ind = len(All_Jobs)
            All_Jobs.append(Job(p, f, job[0], job[1], 0))
            if j == len(Products_data[p]) - 1:
                All_Jobs[ind].last = 1

model: Model = Model(sense=MINIMIZE, solver_name=GRB)
X = {}
for m in range(len(All_Machines)):
    machine_m = All_Machines[m]
    for i in range(len(All_Jobs)):
        job_i = All_Jobs[i]
        if job_i.machine_type == machine_m.type:
            for d in range(D):
                X[i, -1, m, d] = model.add_var('x_{},d{},{},{}'.format(i, m, m, d),
                                               var_type=BINARY)
for i in range(len(All_Jobs)):
    for j in range(len(All_Jobs)):
        job_i = All_Jobs[i]
        job_j = All_Jobs[j]
        if i != j and job_i.machine_type == job_j.machine_type:
            for m in range(len(All_Machines)):
                machine_m = All_Machines[m]
                if machine_m.type == job_i.machine_type:
                    for d in range(D):
                        X[i, j, m, d] = model.add_var('x_{},{},{},{}'.format(i, j, m, d),
                                                      var_type=BINARY)

for d in range(D):
    for i in range(len(All_Jobs)):
        model.add_constr(xsum(x for key, x in X.items()
                         if key[0] == i and key[3] == d) <= 1)
        sum_list = [x for key, x in X.items() if key[1] == i and key[3] == d]
        if len(sum_list) > 0:
            model.add_constr(xsum(sum_list) <= 1)
    for m in range(len(All_Machines)):
        model.add_constr(xsum(x for key, x in X.items()
                         if key[1] == -1 and key[2] == m and key[3] == d) <= 1)

for key_x, x in X.items():
    i = key_x[0]
    j = key_x[1]
    m = key_x[2]
    d = key_x[3]
    if j != -1:
        model.add_constr(x <= xsum(xj for xj_key, xj in X.items()
                                   if xj_key[1] != i and xj_key[0] == j and xj_key[3] == d and xj_key[2] == m))

T = {}
for i in range(len(All_Jobs)):
    for m in range(len(All_Machines)):
        for d in range(D):
            T[i, m, d] = model.add_var('t_{},{},{}'.format(
                i, m, d), var_type=INTEGER, lb=0, ub=24)
for key_x, x in X.items():
    i = key_x[0]
    j = key_x[1]
    m = key_x[2]
    d = key_x[3]
    model.add_constr(T[i, m, d] <= BigM * xsum(x for key, x in X.items() if key[0] == i and key[2] == m
                                               and key[3] == d))
    if j > -1:
        model.add_constr(T[i, m, d] >= BigM * (X[i, j, m, d] -
                         1) + T[j, m, d] + All_Jobs[i].duration)
    else:
        model.add_constr(T[i, m, d] >= BigM *
                         (X[i, j, m, d] - 1) + All_Jobs[i].duration)

V = {}
for m in range(len(All_Machines)):
    machine_m = All_Machines[m]
    for d in range(D):
        V[m, d] = model.add_var('v_{},{}'.format(
            m, d), var_type=INTEGER, lb=0, ub=8, obj=C_ov * machine_m.cost)
        for key, x in X.items():
            if key[2] == m and key[3] == d:
                model.add_constr(V[m, d] + I_hr >= T[key[0], m, d])

Z = {}
for m in range(len(All_Machines)):
    machine_m = All_Machines[m]
    Z[m] = model.add_var('z_{}'.format(
        m), var_type=BINARY, obj=D * machine_m.cost)
    model.add_constr(Z[m] <= xsum(x for key, x in X.items()
                     if key[1] == -1 and key[2] == m))
    model.add_constr(BigM * Z[m] >= xsum(x for key,
                     x in X.items() if key[1] == -1 and key[2] == m))

for d in range(D):
    for i in range(len(All_Jobs) - 1):
        job_i = All_Jobs[i]
        k = i + 1
        job_k = All_Jobs[k]
        if job_i.product == job_k.product and job_i.fproduct == job_k.fproduct:
            mi_type = job_i.machine_type
            mk_type = job_k.machine_type
            model.add_constr(xsum(x_i for x_i_key, x_i in X.items() if x_i_key[0] == i and x_i_key[3] == d)
                             >= xsum(x_k for x_k_key, x_k in X.items() if x_k_key[0] == k and x_k_key[3] == d))
            model.add_constr(xsum(t for key, t in T.items() if key[0] == k and key[2] == d
                                  and All_Machines[key[1]].type == mk_type)
                             >= xsum(tt for tkey, tt in T.items() if tkey[0] == i and tkey[2] == d
                                     and All_Machines[tkey[1]].type == mi_type) + job_k.duration,
                             name='C{}-{}'.format(d, i))

for p in range(No_p):
    for j in range(len(All_Jobs)):
        job_j = All_Jobs[j]
        if job_j.product == p and job_j.last == 1:
            if p < 3:
                for d in range(D):
                    model.add_constr(
                        xsum(x for key, x in X.items() if key[0] == j and key[3] == d) >= 1)
            else:
                model.add_constr(xsum(x for key, x in X.items()
                                 if key[0] == j) >= 3 * D / 4)

for d in range(D):
    model.add_constr(xsum(x for key, x in X.items()
                          if All_Jobs[key[0]].product == 3 and key[1] != -1 and key[3] == d) <= 0)

model.max_gap = 4
status = model.optimize(90)

for d in range(D):
    for key, x in X.items():
        if key[3] == d and x.x > 0.99:
            i = key[0]
            j = key[1]
            p1 = All_Jobs[i].product
            pf1 = All_Jobs[i].fproduct
            m = key[2]
            m_type = All_Machines[m].type
            m_ftype = All_Machines[m].ftype
            p2 = All_Jobs[j].product
            pf2 = All_Jobs[j].fproduct
            print("D{} - Machine M{}-{} - P{}-{} - t{} : t{}".format(d + 1, m_type + 1, m_ftype + 1,
                                                                     p1 + 1, pf1 + 1,
                                                                     T[i, m, d].x -
                                                                     All_Jobs[i].duration,
                                                                     T[i, m, d].x))
