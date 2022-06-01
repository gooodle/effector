"""Goal: show that if data non-uniformly distributed, you have to find the K that matches the piecewise linear regions.
This is not feasible in all cases. Piecewise linear regions, under normal circumstances, are have not equal length.
"""

import numpy as np
import examples.example_utils as utils

# define piecewise linear function
def create_model_params():
    def find_a(params, x_start):
        params[0]["a"] = x_start
        for i, param in enumerate(params):
            if i < len(params) - 1:
                a_next = param["a"] + (param["to"] - param["from"]) * param["b"]
                params[i + 1]["a"] = a_next

    params = [{"b":10, "from": 0., "to": 5.},
              {"b":-10, "from": 5., "to": 10.},
              {"b":0. , "from": 10., "to": 100}]

    x_start = -25.
    find_a(params, x_start)
    return params


# generate samples
def generate_samples(N):
    eps = 1e-05
    x1 = np.random.uniform(0., 5, size=int(N / 3))
    x2 = np.random.uniform(5, 10, size=int(N / 3))
    x3 = np.random.uniform(10, 99, size=int(N / 3))
    x = np.expand_dims(np.concatenate((np.array([0.0]), x1, x2, x3, np.array([100-eps]))), axis=-1)
    return x

# experiment parameters
N = 5000
noise_level = 3.
K_max_fixed = 30
K_max_var = 30
min_points_per_bin = 10

# set seed
seed = 4834545
np.random.seed(seed)

# define functions
model_params = create_model_params()
model = utils.create_model(model_params)
model_jac = utils.create_noisy_jacobian(model_params, noise_level, seed)

# generate data and data effect
data = generate_samples(N=N)
y = model(data)
data_effect = model_jac(data)

# plot data effects and gt effect
utils.plot_gt_effect(data, y)
utils.plot_data_effect(data, data_effect)

# compute loss and mse for many different K
dale_fixed = utils.fit_multiple_K(data, model, model_jac, K_max_fixed, min_points_per_bin, method="fixed-size")
dale_variable = utils.fit_multiple_K(data, model, model_jac, K_max_var, min_points_per_bin, method="variable-size")

# plot loss
utils.plot_loss(dale_fixed)

# plot best fixed solution
best_fixed = np.nanargmin([dale.dale_params["feature_0"]["loss"] for dale in dale_fixed])
dale_fixed[best_fixed].plot(s=0, gt=model, gt_bins=utils.create_gt_bins(model_params), block=False)

# plot best variable size solution
best_var = np.nanargmin([dale.dale_params["feature_0"]["loss"] for dale in dale_variable])
dale_variable[best_var].plot(s=0, gt=model, gt_bins=utils.create_gt_bins(model_params), block=False)
