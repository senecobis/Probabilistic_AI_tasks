import os
import typing
import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor

# from sklearn.gaussian_process.kernels import *
import sklearn.gaussian_process.kernels as ker
import matplotlib.pyplot as plt
from matplotlib import cm
import time
from collections import defaultdict
from random import sample


# Set `EXTENDED_EVALUATION` to `True` in order to visualize your predictions.
EXTENDED_EVALUATION = False
EVALUATION_GRID_POINTS = 300  # Number of grid points used in extended evaluation
EVALUATION_GRID_POINTS_3D = 50  # Number of points displayed in 3D during evaluation


# Cost function constants
COST_W_UNDERPREDICT = 25.0
COST_W_NORMAL = 1.0
COST_W_OVERPREDICT = 10.0


class Model(object):
    """
    Model for this task.
    You need to implement the fit_model and predict methods
    without changing their signatures, but are allowed to create additional methods.
    """

    def __init__(self):
        """
        Initialize your model here.
        We already provide a random number generator for reproducibility.
        """
        self.rng = np.random.default_rng(seed=0)

        # TODO: Add custom initialization for your model here if necessary

    def sample_grid(self, X, Y, Z, rows=5, cols=5, max_points_per_cell=100):
        x_bound = [min(X), max(X)]
        y_bound = [min(Y), max(Y)]

        res_x = (x_bound[1] - x_bound[0]) / cols
        res_y = (y_bound[1] - y_bound[0]) / rows
        LUT_data = defaultdict(lambda: list())
        for idx, z in enumerate(Z):
            x = X[idx]
            y = Y[idx]
            col = x // res_x
            row = y // res_y
            LUT_data[(row, col)].append((x, y, z))

        sampled_points = []
        for r in range(rows):
            for c in range(cols):
                points = LUT_data[(r, c)]
                sampled_points.extend(
                    sample(points, k=min(max_points_per_cell, len(points)))
                )
        return np.array(sampled_points)

    def make_predictions(
        self, test_features: np.ndarray, add_constant=2.2
    ) -> typing.Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Predict the pollution concentration for a given set of locations.
        :param test_features: Locations as a 2d NumPy float array of shape (NUM_SAMPLES, 2)
        :return:
            Tuple of three 1d NumPy float arrays, each of shape (NUM_SAMPLES,),
            containing your predictions, the GP posterior mean, and the GP posterior stddev (in that order)
        """

        # TODO: Use your GP to estimate the posterior mean and stddev for each location here
        gp_mean = np.mean(test_features)

        # TODO: Use the GP posterior to form your predictions here
        predictions, gp_std = self.gpr.predict(test_features, return_std=True)

        predictions += add_constant

        return predictions, gp_mean, gp_std

    def fitting_model(
        self,
        train_GT,
        train_features,
        length_scale=0.09,
        alpha=2.0,
        length_scale_bounds=(1e-05, 100000.0),
        alpha_bounds=(1e-05, 100000.0),
        tot_points=10000,
        rows=20,
        cols=20,
    ):
        """
        Fit your model on the given training data.
        :param train_features: Training features as a 2d NumPy float array of shape (NUM_SAMPLES, 2)
        :param train_GT: Training pollution concentrations as a 1d NumPy float array of shape (NUM_SAMPLES,)
        """
        curr_time = time.time()

        train_lon = train_features[:, 0]
        train_lat = train_features[:, 1]
        max_points_cell = tot_points // (rows * cols)

        sampled_points = self.sample_grid(
            train_lon,
            train_lat,
            train_GT,
            rows=rows,
            cols=cols,
            max_points_per_cell=max_points_cell,
        )

        select_train_feat = sampled_points[..., 0:2]
        select_train_labels = sampled_points[:, 2]

        # TODO: Fit your model here
        kernel = ker.RationalQuadratic(
            length_scale=length_scale,
            alpha=alpha,
            length_scale_bounds=length_scale_bounds,
            alpha_bounds=alpha_bounds,
        )

        print("fitting model")
        self.gpr = GaussianProcessRegressor(
            kernel=kernel, alpha=0.01, n_restarts_optimizer=50, random_state=0
        ).fit(select_train_feat, select_train_labels)
        print("fit runtime : ", time.time() - curr_time)


def cost_function(ground_truth: np.ndarray, predictions: np.ndarray) -> float:
    """
    Calculates the cost of a set of predictions.

    :param ground_truth: Ground truth pollution levels as a 1d NumPy float array
    :param predictions: Predicted pollution levels as a 1d NumPy float array
    :return: Total cost of all predictions as a single float
    """
    assert (
        ground_truth.ndim == 1
        and predictions.ndim == 1
        and ground_truth.shape == predictions.shape
    )

    # Unweighted cost
    cost = (ground_truth - predictions) ** 2
    weights = np.ones_like(cost) * COST_W_NORMAL

    # Case i): underprediction
    mask_1 = predictions < ground_truth
    weights[mask_1] = COST_W_UNDERPREDICT

    # Case ii): significant overprediction
    mask_2 = predictions >= 1.2 * ground_truth
    weights[mask_2] = COST_W_OVERPREDICT

    # Weigh the cost and return the average
    return np.mean(cost * weights)


def perform_extended_evaluation(model: Model, output_dir: str = "/results"):
    """
    Visualizes the predictions of a fitted model.
    :param model: Fitted model to be visualized
    :param output_dir: Directory in which the visualizations will be stored
    """
    print("Performing extended evaluation")
    fig = plt.figure(figsize=(30, 10))
    fig.suptitle("Extended visualization of task 1")

    # Visualize on a uniform grid over the entire coordinate system
    grid_lat, grid_lon = np.meshgrid(
        np.linspace(0, EVALUATION_GRID_POINTS - 1, num=EVALUATION_GRID_POINTS)
        / EVALUATION_GRID_POINTS,
        np.linspace(0, EVALUATION_GRID_POINTS - 1, num=EVALUATION_GRID_POINTS)
        / EVALUATION_GRID_POINTS,
    )
    visualization_xs = np.stack((grid_lon.flatten(), grid_lat.flatten()), axis=1)

    # Obtain predictions, means, and stddevs over the entire map
    predictions, gp_mean, gp_stddev = model.make_predictions(visualization_xs)
    predictions = np.reshape(
        predictions, (EVALUATION_GRID_POINTS, EVALUATION_GRID_POINTS)
    )
    gp_mean = np.reshape(gp_mean, (EVALUATION_GRID_POINTS, EVALUATION_GRID_POINTS))
    gp_stddev = np.reshape(gp_stddev, (EVALUATION_GRID_POINTS, EVALUATION_GRID_POINTS))

    vmin, vmax = 0.0, 65.0
    vmax_stddev = 35.5

    # Plot the actual predictions
    ax_predictions = fig.add_subplot(1, 3, 1)
    predictions_plot = ax_predictions.imshow(predictions, vmin=vmin, vmax=vmax)
    ax_predictions.set_title("Predictions")
    fig.colorbar(predictions_plot)

    # Plot the raw GP predictions with their stddeviations
    ax_gp = fig.add_subplot(1, 3, 2, projection="3d")
    ax_gp.plot_surface(
        X=grid_lon,
        Y=grid_lat,
        Z=gp_mean,
        facecolors=cm.get_cmap()(gp_stddev / vmax_stddev),
        rcount=EVALUATION_GRID_POINTS_3D,
        ccount=EVALUATION_GRID_POINTS_3D,
        linewidth=0,
        antialiased=False,
    )
    ax_gp.set_zlim(vmin, vmax)
    ax_gp.set_title("GP means, colors are GP stddev")

    # Plot the standard deviations
    ax_stddev = fig.add_subplot(1, 3, 3)
    stddev_plot = ax_stddev.imshow(gp_stddev, vmin=vmin, vmax=vmax_stddev)
    ax_stddev.set_title("GP estimated stddev")
    fig.colorbar(stddev_plot)

    # Save figure to pdf
    figure_path = os.path.join(output_dir, "extended_evaluation.pdf")
    fig.savefig(figure_path)
    print(f"Saved extended evaluation to {figure_path}")

    plt.show()


def main():
    # Load the training dateset and test features
    dir_path = os.path.dirname(os.path.realpath(__file__))
    train_features = np.loadtxt(dir_path + "/train_x.csv", delimiter=",", skiprows=1)
    train_GT = np.loadtxt(dir_path + "/train_y.csv", delimiter=",", skiprows=1)
    test_features = np.loadtxt(dir_path + "/test_x.csv", delimiter=",", skiprows=1)

    print("ground truth parameters", train_GT.min(), train_GT.max(), train_GT.mean())

    # Fit the model
    print("Fitting model")
    model = Model()
    model.fitting_model(train_GT, train_features)

    # Predict on the test features
    print("Predicting on test features")

    predictions, gp_mean, gp_std = model.make_predictions(test_features)
    print(predictions, predictions.min(), predictions.max())

    cost_of_pred = cost_function(train_GT, model.make_predictions(train_features)[0])
    print(cost_of_pred)

    if EXTENDED_EVALUATION:
        perform_extended_evaluation(model, output_dir=".")


if __name__ == "__main__":
    main()
