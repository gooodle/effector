import typing
import effector.utils as utils
import effector.visualization as vis
import effector.binning_methods as bm
import effector.helpers as helpers
from effector.global_effect import GlobalEffect
import numpy as np


class RHALE(GlobalEffect):
    def __init__(
        self,
        data: np.ndarray,
        model: callable,
        model_jac: None | callable = None,
        axis_limits: None | np.ndarray = None,
        data_effect: None | np.ndarray = None,
        avg_output: None | float = None,
        feature_names: None | list = None,
        target_name: None | str = None,
    ):
        """
        Constructor for RHALE.

        Definition:
            RHALE is defined as:
            $$
            \hat{f}^{RHALE}(x_s) = TODO
            $$

            The heterogeneity is:
            $$
            TODO
            $$

        Notes:
            The required parameters are `data` and `model`. The rest are optional.

        Args:
            data: the design matrix

                - shape: `(N,D)`
            model: the black-box model. Must be a `Callable` with:

                - input: `ndarray` of shape `(N, D)`
                - output: `ndarray` of shape `(N, )`

            model_jac: the Jacobian of the model. Must be a `Callable` with:

                - input: `ndarray` of shape `(N, D)`
                - output: `ndarray` of shape `(N, D)`

            axis_limits: The limits of the feature effect plot along each axis

                - use a `ndarray` of shape `(2, D)`, to specify them manually
                - use `None`, to be inferred from the data

            data_effect:
                - if np.ndarray, the model Jacobian computed on the `data`
                - if None, the Jacobian will be computed using model_jac

            avg_output: the average output of the model on the data

                - use a `float`, to specify it manually
                - use `None`, to be inferred as `np.mean(model(data))`

            feature_names: The names of the features

                - use a `list` of `str`, to specify the name manually. For example: `                  ["age", "weight", ...]`
                - use `None`, to keep the default names: `["x_0", "x_1", ...]`

            target_name: The name of the target variable

                - use a `str`, to specify it name manually. For example: `"price"`
                - use `None`, to keep the default name: `"y"`
        """
        self.model_jac = model_jac

        # if data_effect is None, it will be computed after compile
        self.data_effect = data_effect

        super(RHALE, self).__init__(
            data, model, axis_limits, avg_output, feature_names, target_name
        )

    def compile(self):
        """Prepare everything for fitting, i.e., compute the gradients on data points.
        """
        if self.data_effect is None and self.model_jac is not None:
            self.data_effect = self.model_jac(self.data)
        elif self.data_effect is None and self.model_jac is None:
            self.data_effect = utils.compute_jacobian_numerically(self.model, self.data)

    def _fit_feature(self, feature: int, binning_method) -> typing.Dict:
        if self.data_effect is None:
            self.compile()

        # drop points outside of limits
        self.data = self.data[self.data[:, feature] >= self.axis_limits[0, feature]]
        self.data = self.data[self.data[:, feature] <= self.axis_limits[1, feature]]
        ind = np.logical_and(
            self.data[:, feature] >= self.axis_limits[0, feature],
            self.data[:, feature] <= self.axis_limits[1, feature],
        )
        data = self.data[ind, :]
        data_effect = self.data_effect[ind, :]

        # bin estimation
        bin_est = bm.find_limits(
            data, data_effect, feature, self.axis_limits, binning_method
        )
        bin_name = bin_est.__class__.__name__

        # assert bins can be computed else raise error
        assert bin_est.limits is not False, (
            "Impossible to compute bins with enough points for feature "
            + str(feature + 1)
            + " and binning strategy: "
            + bin_name
            + ". Change bin strategy or "
            "the parameters of the method"
        )

        # compute the bin effect
        dale_params = utils.compute_ale_params(
            data[:, feature], data_effect[:, feature], bin_est.limits
        )
        dale_params["alg_params"] = binning_method
        return dale_params

    def fit(
        self,
        features: int | str | list = "all",
        binning_method: str | bm.DynamicProgramming | bm.Greedy | bm.Fixed = "greedy",
        centering: bool | str = False,
    ) -> None:
        """Fit the model.

        Args:
            features (int, str, list): the features to fit.
                - If set to "all", all the features will be fitted.

            binning_method (str): the binning method to use.

                - If set to "greedy" or bm.Greedy, the greedy binning method will be used.
                - If set to "dynamic" or bm.DynamicProgramming, the dynamic programming binning method will be used.
                - If set to "fixed" or bm.Fixed, the fixed binning method will be used.

            centering: whether to center the RHALE plot

                - If `centering` is `False`, the PDP not centered
                - If `centering` is `True` or `zero_integral`, the PDP is centered around the `y` axis.
                - If `centering` is `zero_start`, the PDP starts from `y=0`.
        """
        features = helpers.prep_features(features, self.dim)
        centering = helpers.prep_centering(centering)
        for s in features:
            self.feature_effect["feature_" + str(s)] = self._fit_feature(
                s, binning_method
            )
            if centering is not False:
                self.norm_const[s] = self._compute_norm_const(s, method=centering)
            self.is_fitted[s] = True
            self.method_args["feature_" + str(s)] = {
                "centering": centering,
            }

    def _eval_unnorm(self, feature: int, x: np.ndarray, heterogeneity: bool = False):
        params = self.feature_effect["feature_" + str(feature)]
        y = utils.compute_accumulated_effect(
            x, limits=params["limits"], bin_effect=params["bin_effect"], dx=params["dx"]
        )
        if heterogeneity:
            std = utils.compute_accumulated_effect(
                x,
                limits=params["limits"],
                bin_effect=np.sqrt(params["bin_variance"]),
                dx=params["dx"],
            )
            std_err = utils.compute_accumulated_effect(
                x,
                limits=params["limits"],
                bin_effect=np.sqrt(params["bin_estimator_variance"]),
                dx=params["dx"],
            )

            return y, std, std_err
        else:
            return y

    def plot(
        self,
        feature: int = 0,
        heterogeneity: typing.Union[bool, str] = False,
        centering: typing.Union[bool, str] = False,
        scale_x: typing.Union[None, dict] = None,
        scale_y: typing.Union[None, dict] = None,
        show_avg_output: bool = False,
        y_limits: None | list = None
    ):
        """
        Plot RHALE effect.

        Parameters:
            feature: the feature to plot
            heterogeneity: whether to output the heterogeneity of the RHALE plot

                - If `heterogeneity` is `False`, no heterogeneity is plotted
                - If `heterogeneity` is `True` or `"std"`, the standard deviation of the RHALE is plotted

            centering: whether to center the PDP

                - If `centering` is `False`, the RHALE is not centered
                - If `centering` is `True` or `zero_integral`, the RHALE is centered around the `y` axis.
                - If `centering` is `zero_start`, the RHALE starts from `y=0`.

            scale_x: None or Dict with keys ['std', 'mean']

                - If set to None, no scaling will be applied.
                - If set to a dict, the x-axis will be scaled by the standard deviation and the mean.

            scale_y: None or Dict with keys ['std', 'mean']

                - If set to None, no scaling will be applied.
                - If set to a dict, the y-axis will be scaled by the standard deviation and the mean.

            show_avg_output: bool, if True, the average output is shown
            y_limits: None or tuple, the limits of the y-axis

                - If set to None, the limits of the y-axis are set automatically
                - If set to a tuple, the limits are manually set
        """
        heterogeneity = helpers.prep_confidence_interval(heterogeneity)
        centering = helpers.prep_centering(centering)

        # hack to fit the feature if not fitted
        self.eval(
            feature, np.array([self.axis_limits[0, feature]]), centering=centering
        )

        if show_avg_output:
            avg_output = helpers.prep_avg_output(self.data, self.model, self.avg_output, scale_y)
        else:
            avg_output = None

        vis.ale_plot(
            self.feature_effect["feature_" + str(feature)],
            self.eval,
            feature,
            centering=centering,
            error=heterogeneity,
            scale_x=scale_x,
            scale_y=scale_y,
            title="RHALE Plot",
            avg_output=avg_output,
            feature_names=self.feature_names,
            target_name=self.target_name,
            y_limits=y_limits
        )
