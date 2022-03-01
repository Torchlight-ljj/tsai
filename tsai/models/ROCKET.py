# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/111_models.ROCKET.ipynb (unless otherwise specified).

__all__ = ['ROCKET', 'create_rocket_features', 'get_rocket_features', 'RocketClassifier', 'load_rocket',
           'RocketRegressor']

# Cell
import sklearn
from sklearn.linear_model import RidgeClassifierCV, RidgeCV
from sklearn.metrics import make_scorer
from ..imports import *
from ..data.external import *
from .layers import *
warnings.filterwarnings("ignore", category=FutureWarning)

# Cell
try:
    import numba
    from numba import njit, prange

    # This is an unofficial ROCKET implementation in Pytorch developed by Ignacio Oguiza - oguiza@gmail.com based on:
    # Angus Dempster, Francois Petitjean, Geoff Webb
    # Dempster A, Petitjean F, Webb GI (2019) ROCKET: Exceptionally fast and
    # accurate time series classification using random convolutional kernels.
    # arXiv:1910.13051
    # Official repo: https://github.com/angus924/rocket

    # changes:
    # - added kss parameter to generate_kernels
    # - convert X to np.float64

    def generate_kernels(input_length, num_kernels, kss=[7, 9, 11], pad=True, dilate=True):
        candidate_lengths = np.array((kss))
        # initialise kernel parameters
        weights = np.zeros((num_kernels, candidate_lengths.max())) # see note
        lengths = np.zeros(num_kernels, dtype = np.int32) # see note
        biases = np.zeros(num_kernels)
        dilations = np.zeros(num_kernels, dtype = np.int32)
        paddings = np.zeros(num_kernels, dtype = np.int32)
        # note: only the first *lengths[i]* values of *weights[i]* are used
        for i in range(num_kernels):
            length = np.random.choice(candidate_lengths)
            _weights = np.random.normal(0, 1, length)
            bias = np.random.uniform(-1, 1)
            if dilate: dilation = 2 ** np.random.uniform(0, np.log2((input_length - 1) // (length - 1)))
            else: dilation = 1
            if pad: padding = ((length - 1) * dilation) // 2 if np.random.randint(2) == 1 else 0
            else: padding = 0
            weights[i, :length] = _weights - _weights.mean()
            lengths[i], biases[i], dilations[i], paddings[i] = length, bias, dilation, padding
        return weights, lengths, biases, dilations, paddings

    @njit(fastmath = True)
    def apply_kernel(X, weights, length, bias, dilation, padding):
        # zero padding
        if padding > 0:
            _input_length = len(X)
            _X = np.zeros(_input_length + (2 * padding))
            _X[padding:(padding + _input_length)] = X
            X = _X
        input_length = len(X)
        output_length = input_length - ((length - 1) * dilation)
        _ppv = 0 # "proportion of positive values"
        _max = np.NINF
        for i in range(output_length):
            _sum = bias
            for j in range(length):
                _sum += weights[j] * X[i + (j * dilation)]
            if _sum > 0:
                _ppv += 1
            if _sum > _max:
                _max = _sum
        return _ppv / output_length, _max

    @njit(parallel = True, fastmath = True)
    def apply_kernels(X, kernels):
        X = X.astype(np.float64)
        weights, lengths, biases, dilations, paddings = kernels
        num_examples = len(X)
        num_kernels = len(weights)
        # initialise output
        _X = np.zeros((num_examples, num_kernels * 2)) # 2 features per kernel
        for i in prange(num_examples):
            for j in range(num_kernels):
                _X[i, (j * 2):((j * 2) + 2)] = \
                apply_kernel(X[i], weights[j][:lengths[j]], lengths[j], biases[j], dilations[j], paddings[j])
        return _X

except ImportError:
    print("You need to install numba to be able to use apply_kernels")

# Cell
class ROCKET(nn.Module):
    """RandOm Convolutional KErnel Transform

    ROCKET is a GPU Pytorch implementation of the ROCKET functions generate_kernels
    and apply_kernels that can be used  with univariate and multivariate time series.
    """

    def __init__(self, c_in, seq_len, n_kernels=10_000, kss=[7, 9, 11], device=None, verbose=False):

        '''
        Input: is a 3d torch tensor of type torch.float32. When used with univariate TS,
        make sure you transform the 2d to 3d by adding unsqueeze(1).
        c_in: number of channels or features. For univariate c_in is 1.
        seq_len: sequence length
        '''
        super().__init__()
        device = ifnone(device, default_device())
        kss = [ks for ks in kss if ks < seq_len]
        convs = nn.ModuleList()
        for i in range(n_kernels):
            ks = np.random.choice(kss)
            dilation = 2**np.random.uniform(0, np.log2((seq_len - 1) // (ks - 1)))
            padding = int((ks - 1) * dilation // 2) if np.random.randint(2) == 1 else 0
            weight = torch.randn(1, c_in, ks)
            weight -= weight.mean()
            bias = 2 * (torch.rand(1) - .5)
            layer = nn.Conv1d(c_in, 1, ks, padding=2 * padding, dilation=int(dilation), bias=True)
            layer.weight = torch.nn.Parameter(weight, requires_grad=False)
            layer.bias = torch.nn.Parameter(bias, requires_grad=False)
            convs.append(layer)
        self.convs = convs
        self.n_kernels = n_kernels
        self.kss = kss
        self.to(device=device)
        self.verbose=verbose

    def forward(self, x):
        _output = []
        for i in progress_bar(range(self.n_kernels), display=self.verbose, leave=False, comment='kernel/kernels'):
            out = self.convs[i](x).cpu()
            _max = out.max(dim=-1)[0]
            _ppv = torch.gt(out, 0).sum(dim=-1).float() / out.shape[-1]
            _output.append(_max)
            _output.append(_ppv)
        return torch.cat(_output, dim=1)

# Cell
def create_rocket_features(dl, model, verbose=False):
    """Args:
        model     : ROCKET model instance
        dl        : single TSDataLoader (for example dls.train or dls.valid)
    """
    _x_out = []
    _y_out = []
    for i,(xb,yb) in enumerate(progress_bar(dl, display=verbose, leave=False, comment='batch/batches')):
        _x_out.append(model(xb).cpu())
        _y_out.append(yb.cpu())
    return torch.cat(_x_out).numpy(), torch.cat(_y_out).numpy()

get_rocket_features = create_rocket_features

# Cell
class RocketClassifier(sklearn.pipeline.Pipeline):
    """Time series classification using ROCKET features and a linear classifier"""

    def __init__(self, num_kernels=10_000, normalize_input=True, random_state=None,
                 alphas=np.logspace(-3, 3, 7), normalize_features=True, memory=None, verbose=False, scoring=None, class_weight=None, **kwargs):
        """
        RocketClassifier is recommended for up to 10k time series.
        For a larger dataset, you can use ROCKET (in Pytorch).
        scoring = None --> defaults to accuracy.

        Rocket args:
            num_kernels     : int, number of random convolutional kernels (default 10,000)
            normalize_input : boolean, whether or not to normalise the input time series per instance (default True)
            random_state    : int (ignored unless int due to compatability with Numba), random seed (optional, default None)

        """

        try:
            import sktime
            from sktime.transformations.panel.rocket import Rocket

            self.steps = [('rocket', Rocket(num_kernels=num_kernels, normalise=normalize_input, random_state=random_state)),
                          ('ridgeclassifiercv', RidgeClassifierCV(alphas=alphas, normalize=normalize_features, scoring=scoring,
                                                                  class_weight=class_weight, **kwargs))]
            store_attr()
            self._validate_steps()

        except ImportError:
            print("You need to install sktime to be able to use RocketClassifier")

    def __repr__(self):
        return f'Pipeline(steps={self.steps.copy()})'

    def save(self, fname='Rocket', path='./models'):
        path = Path(path)
        filename = path/fname
        with open(f'{filename}.pkl', 'wb') as output:
            pickle.dump(self, output, pickle.HIGHEST_PROTOCOL)

# Cell
def load_rocket(fname='Rocket', path='./models'):
    path = Path(path)
    filename = path/fname
    with open(f'{filename}.pkl', 'rb') as input:
        output = pickle.load(input)
    return output

# Cell
class RocketRegressor(sklearn.pipeline.Pipeline):
    """Time series regression using ROCKET features and a linear regressor"""

    def __init__(self, num_kernels=10_000, normalize_input=True, random_state=None,
                 alphas=np.logspace(-3, 3, 7), normalize_features=True, memory=None, verbose=False, scoring=None, **kwargs):
        """
        RocketRegressor is recommended for up to 10k time series.
        For a larger dataset, you can use ROCKET (in Pytorch).
        scoring = None --> defaults to r2.

        Args:
            num_kernels     : int, number of random convolutional kernels (default 10,000)
            normalize_input : boolean, whether or not to normalise the input time series per instance (default True)
            random_state    : int (ignored unless int due to compatability with Numba), random seed (optional, default None)
        """

        try:
            import sktime
            from sktime.transformations.panel.rocket import Rocket

            self.steps = [('rocket', Rocket(num_kernels=num_kernels, normalise=normalize_input, random_state=random_state)),
                      ('ridgecv', RidgeCV(alphas=alphas, normalize=normalize_features, scoring=scoring, **kwargs))]
            store_attr()
            self._validate_steps()

        except ImportError:
            print("You need to install sktime to be able to use RocketClassifier")

    def __repr__(self):
        return f'Pipeline(steps={self.steps.copy()})'

    def save(self, fname='Rocket', path='./models'):
        path = Path(path)
        filename = path/fname
        with open(f'{filename}.pkl', 'wb') as output:
            pickle.dump(self, output, pickle.HIGHEST_PROTOCOL)