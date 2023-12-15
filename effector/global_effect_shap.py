import typing
import effector.visualization as vis
import effector.helpers as helpers
import effector.utils as utils
from effector.global_effect import GlobalEffect
import numpy as np
import shap
from scipy.interpolate import UnivariateSpline
import matplotlib.pyplot as plt


class SHAPDependence(GlobalEffect):
    def __init__(
        self,
        data: np.ndarray,
        model: callable,
        axis_limits: None | np.ndarray = None,
        avg_output: None | float = None,
        feature_names: None | list[str] = None,
        target_name: None | str = None,
    ):
        """
        Constructor of the SHAPDependence class.

        Definition:
            The value of a coalition of $S$ features is estimated as:
            $$
            \hat{v}(S) = {1 \over N} \sum_{i=1}^N  f(x_S \cup x_C^i) - f(x^i)
            $$
            The value of a coalition $S$ is the average (over all instances) difference on the output of the model between setting features in $S$ to be $x_S$, i.e., $\mathbf{x} = (\mathbf{x}_S, \mathbf{x}_C^i)$ and leaving the instance as it is, i.e., $\mathbf{x}^i = (\mathbf{x}_S^i, \mathbf{x}_C^i)$.

            The contribution of a feature $j$ added to a coalition $S$ is estimated as:
            $$
            \hat{\Delta}_{S, j} = \hat{v}(S \cup \{j\}) - \hat{v}(S)
            $$

            The SHAP value of a feature $j$ with value $x_j$ is the average contribution of feature $j$ across all possible coalitions with a weight $w_{S, j}$:

            $$
            \hat{\phi}_j(x_j) = {1 \over N} \sum_{S \subseteq \{1, \dots, D\} \setminus \{j\}} w_{S, j} \hat{\Delta}_{S, j}
            $$

            where $w_{S, j}$ assures that the contribution of feature $j$ is the same for all coalitions of the same size. For example, there are $D-1$ ways for $x_j$ to enter a coalition of $|S| = 1$ feature, so $w_{S, j} = {1 \over D (D-1)}$ for each of them. In contrast, there is only one way for $x_j$ to enter a coaltion of $|S|=0$ (to be the first specified feature), so $w_{S, j} = {1 \over D}$.

            The SHAP Dependence Plot (SHAP-DP) is simply a scatter plot of $\{x_j^i, \hat{\phi}_j(x_j^i)\}_{i=1}^N$. To make it a continuous curve, we fit a spline to the scatter plot using the `UnivariateSpline` function from `scipy.interpolate`.

        Notes:
            * The required variables are `data` and `model`.
            * SHAP values are computed using the `shap` package. Due to computational reasons, we use the `PermutationExplainer` method.
            * SHAP values are centered by default, i.e., the average SHAP value is subtracted from the SHAP values.
            * More details on the SHAP values can be found in the [original paper](https://arxiv.org/abs/1705.07874) and in the book [Interpreting Machine Learning Models with SHAP](https://christophmolnar.com/books/shap/)

        Args:
            data: the design matrix

                - shape: `(N,D)`
            model: the black-box model. Must be a `Callable` with:

                - input: `ndarray` of shape `(N, D)`
                - output: `ndarray` of shape `(N, )`

            axis_limits: The limits of the feature effect plot along each axis

                - use a `ndarray` of shape `(2, D)`, to specify them manually
                - use `None`, to be inferred from the data

            avg_output: The average output of the model.

                - use a `float`, to specify it manually
                - use `None`, to be inferred as `np.mean(model(data))`

            feature_names: The names of the features

                - use a `list` of `str`, to specify the name manually. For example: `                  ["age", "weight", ...]`
                - use `None`, to keep the default names: `["x_0", "x_1", ...]`

            target_name: The name of the target variable

                - use a `str`, to specify it name manually. For example: `"price"`
                - use `None`, to keep the default name: `"y"`

        """
        super(SHAPDependence, self).__init__(
            data, model, axis_limits, avg_output, feature_names, target_name
        )

    def _fit_feature(
        self,
        feature: int,
        centering: typing.Union[bool, str] = False,
        points_for_fitting_spline: int | str = 100,
        points_used_for_centering: int = 100,
    ) -> typing.Dict:

        # drop points outside of limits
        data = self.data[self.data[:, feature] >= self.axis_limits[0, feature]]

        # prepare nof points
        _, ind_shap = helpers.prep_nof_instances(points_for_fitting_spline, data.shape[0])
        _, ind_cent = helpers.prep_nof_instances(points_used_for_centering, data.shape[0])

        # compute shap values
        data = data[ind_shap, :]
        shap_explainer = shap.Explainer(self.model, data)
        explanation = shap_explainer(data)

        # extract x and y pais
        yy = explanation.values[:, feature]
        xx = data[:, feature]

        # make xx monotonic
        idx = np.argsort(xx)
        xx = xx[idx]
        yy = yy[idx]

        # fit spline_mean to xx, yy pairs
        spline_mean = UnivariateSpline(xx, yy)

        # fit spline_mean to the sqrt of the residuals
        yy_std = np.abs(yy - spline_mean(xx))
        spline_std = UnivariateSpline(xx, yy_std)

        # compute norm constant
        if centering == "zero_integral":
            x_norm = np.linspace(xx[0], xx[-1], points_used_for_centering)
            y_norm = spline_mean(x_norm)
            norm_const = np.trapz(y_norm, x_norm) / (xx[-1] - xx[0])
        elif centering == "zero_start":
            norm_const = spline_mean(xx[0])
        else:
            norm_const = helpers.EMPTY_SYMBOL

        ret_dict = {
            "spline_mean": spline_mean,
            "spline_std": spline_std,
            "xx": xx,
            "yy": yy,
            "norm_const": norm_const,
        }
        return ret_dict

    def fit(
        self,
        features: int | str | list = "all",
        centering: bool | str = False,
        points_for_fitting_spline: int | str = 100,
        points_for_centering: int | str = 100,
    ) -> None:
        """Fit the SHAP Dependence Plot to the data.

        Notes:
            The SHAP Dependence Plot (SDP) $\hat{f}^{SDP}_j(x_j)$ is a spline fit to
            the dataset $\{(x_j^i, \hat{\phi}_j(x_j^i))\}_{i=1}^N$
            using the `UnivariateSpline` function from `scipy.interpolate`.

            The SHAP standard deviation, $\hat{\sigma}^{SDP}_j(x_j)$, is a spline fit            to the absolute value of the residuals, i.e., to the dataset $\{(x_j^i, |\hat{\phi}_j(x_j^i) - \hat{f}^{SDP}_j(x_j^i)|)\}_{i=1}^N$, using the `UnivariateSpline` function from `scipy.interpolate`.

        Args:
            features: the features to fit.
                - If set to "all", all the features will be fitted.
            centering:
                - If set to False, no centering will be applied.
                - If set to "zero_integral" or True, the integral of the feature effect will be set to zero.
                - If set to "zero_mean", the mean of the feature effect will be set to zero.
            points_for_fitting_spline: number of dataset points used for (a) computing the SHAP values and (b) fitting the spline.

                - If set to `all`, all the dataset points will be used.
            points_for_centering: number of linspaced points along the feature axis used for centering.

                - If set to `all`, all the dataset points will be used.


        Notes:
            SHAP values are by default centered, i.e., $\sum_{i=1}^N \hat{\phi}_j(x_j^i) = 0$. This does not mean that the SHAP _curve_ is centered around zero; this happens only if the $s$-th feature of the dataset instances, i.e., the set $\{x_s^i\}_{i=1}^N$ is uniformly distributed along the $s$-th axis. So, use:

            * `centering=False`, to leave the SHAP values as they are.
            * `centering=True` or `centering=zero_integral`, to center the SHAP curve around the `y` axis.
            * `centering=zero_start`, to start the SHAP curve from `y=0`.

            SHAP values are expensive to compute.
            To speed up the computation consider using a subset of the dataset
            points for computing the SHAP values and for centering the spline.
            The default values (`points_for_fitting_spline=100`
            and `points_for_centering=100`) are a moderate choice.
        """
        centering = helpers.prep_centering(centering)
        features = helpers.prep_features(features, self.dim)

        # new implementation
        for s in features:
            self.feature_effect["feature_" + str(s)] = self._fit_feature(
                s, centering, points_for_fitting_spline, points_for_centering
            )
            self.is_fitted[s] = True

    def eval(
        self,
        feature: int,
        xs: np.ndarray,
        uncertainty: bool = False,
        centering: typing.Union[bool, str] = False,
    ) -> np.ndarray | typing.Tuple[np.ndarray, np.ndarray]:
        """Evaluate the effect of the s-th feature at positions `xs`.

        Args:
            feature: index of feature of interest
            xs: the points along the s-th axis to evaluate the FE plot

              - `np.ndarray` of shape `(T,)`
            uncertainty: whether to return the uncertainty measures.

                  - if `uncertainty=False`, the function returns the mean effect at the given `xs`
                  - If `uncertainty=True`, the function returns `(y, std)` where `y` is the mean effect and `std` is the standard deviation of the mean effect

            centering: whether to center the plot

                - If `centering` is `False`, the SHAP curve is not centered
                - If `centering` is `True` or `zero_integral`, the SHAP curve is centered around the `y` axis.
                - If `centering` is `zero_start`, the SHAP curve starts from `y=0`.

        Returns:
            the mean effect `y`, if `uncertainty=False` (default) or a tuple `(y, std, estimator_var)` otherwise
        """
        centering = helpers.prep_centering(centering)
        if (
            not self.is_fitted[feature]
            or self.feature_effect["feature_" + str(feature)]["norm_const"] == helpers.EMPTY_SYMBOL
            and centering is not False
        ):
            self.fit(features=feature, centering=centering)

        # Check if the lower bound is less than the upper bound
        assert self.axis_limits[0, feature] < self.axis_limits[1, feature]

        yy = self.feature_effect["feature_" + str(feature)]["spline_mean"](xs)

        if centering is not False:
            norm_const = self.feature_effect["feature_" + str(feature)]["norm_const"]
            yy = yy - norm_const

        if uncertainty:
            yy_std = self.feature_effect["feature_" + str(feature)]["spline_std"](xs)
            return yy, yy_std, np.zeros_like(yy_std)
        else:
            return yy

    def plot(
        self,
        feature: int,
        confidence_interval: typing.Union[bool, str] = False,
        centering: typing.Union[bool, str] = False,
        nof_axis_points: int = 30,
        scale_x: typing.Union[None, dict] = None,
        scale_y: typing.Union[None, dict] = None,
        nof_shap_values: typing.Union[int, str] = "all",
        show_avg_output: bool = False,
        y_limits: typing.Union[None, list] = None,
    ) -> None:
        """
        Plot the SHAP Dependence Plot.

        Args:
            feature: index of the plotted feature
            confidence_interval: whether to plot the confidence interval
            centering: whether to center the PDP
            nof_axis_points: number of points on the x-axis to evaluate the PDP plot
            scale_x: dictionary with keys "mean" and "std" for scaling the x-axis
            scale_y: dictionary with keys "mean" and "std" for scaling the y-axis
            nof_shap_values: number of shap values to show on top of the SHAP curve
            show_avg_output: whether to show the average output of the model
            y_limits: limits of the y-axis

        Notes:
            * if `confidence_interval` is `False`, no confidence interval is plotted
            * if `confidence_interval` is `True` or `"std"`, the standard deviation of the shap values is plotted
            * if `confidence_interval` is `shap_values`, the shap values are plotted

        Notes:
            * If `centering` is `False`, the PDP and ICE plots are not centered
            * If `centering` is `True` or `"zero_integral"`, the PDP and the ICE plots are centered wrt to the `y` axis.
            * If `centering` is `"zero_start"`, the PDP and the ICE plots start from `y=0`.

        """
        confidence_interval = helpers.prep_confidence_interval(confidence_interval)
        x = np.linspace(
            self.axis_limits[0, feature], self.axis_limits[1, feature], nof_axis_points
        )

        # get the SHAP curve
        y = self.eval(feature, x, uncertainty=False, centering=centering)

        # get the std of the SHAP curve
        y_std = (
            self.feature_effect["feature_" + str(feature)]["spline_std"](x)
            if confidence_interval == "std"
            else None
        )

        # get some SHAP values
        yy = (
            self.feature_effect["feature_" + str(feature)]["yy"]
            if confidence_interval == "shap_values"
            else None
        )
        xx = (
            self.feature_effect["feature_" + str(feature)]["xx"]
            if confidence_interval == "shap_values"
            else None
        )

        if nof_shap_values != "all" and nof_shap_values < len(xx):
            idx = np.random.choice(len(xx), nof_shap_values, replace=False)
            xx = xx[idx]
            yy = yy[idx]

        avg_output = None if not show_avg_output else self.avg_output

        vis.plot_shap(
            x,
            y,
            xx,
            yy,
            y_std,
            feature,
            confidence_interval=confidence_interval,
            scale_x=scale_x,
            scale_y=scale_y,
            avg_output=avg_output,
            feature_names=self.feature_names,
            target_name=self.target_name,
            y_limits=y_limits
        )
