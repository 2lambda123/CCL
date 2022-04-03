# NOTE: Classes `Hashing` and `Caching` only contain class methods.
# It is usually suggested that such code should have its own namespace
# in the form of distinct functions in a separate module.
# However, these namespaces are deliberately chosen to be like that
# so that pyccl isn't cluttered with many non-cosmological modules.
import sys
import functools
from collections import OrderedDict
import hashlib
import numpy as np
from inspect import signature, isclass


class Hashing:
    """Container class which implements hashing consistently.

    Attributes:
        consistent (``bool``):
            If False, hashes of different processes are randomly salted.
            Defaults to False for speed, but hashes differ across processes.

    .. note::

        Consistent (unsalted) hashing between different processes comes at
        the expense of extra computation time (~200x slower).
        Buitin ``hash`` computes in O(100 ns) while using hashlib with md5
        computes in O(20 μs).
    """
    consistent: bool = False

    @classmethod
    def _finalize(cls, obj, /):
        """Alphabetically sort all dictionaries except ordered dictionaries.
        """
        if isinstance(obj, OrderedDict):
            return tuple(obj)
        return tuple(sorted(obj))

    @classmethod
    def to_hashable(cls, obj, /):
        """Make unhashable objects hashable in a consistent manner."""
        if isclass(obj):
            return obj.__qualname__
        elif isinstance(obj, (tuple, list, set)):
            return tuple([cls.to_hashable(item) for item in obj])
        elif isinstance(obj, np.ndarray):
            return obj.tobytes()
        elif isinstance(obj, dict):
            dic = dict.fromkeys(obj.keys())
            for key, value in obj.items():
                dic[key] = cls.to_hashable(value)
            return cls._finalize(dic.items())
        # nothing left to do; just return the object
        return obj

    @classmethod
    def _hash_consistent(cls, obj, /):
        """Calculate consistent hash value for an input object."""
        hasher = hashlib.md5()
        hasher.update(repr(cls.to_hashable(obj)).encode())
        return int(hasher.digest().hex(), 16)

    @classmethod
    def _hash_generic(cls, obj, /):
        """Generic hash method, which changes between processes."""
        digest = hash(repr(cls.to_hashable(obj))) + sys.maxsize + 1
        return digest

    @classmethod
    def hash_(cls, obj, /):
        if not cls.consistent:
            return cls._hash_generic(obj)
        return cls._hash_consistent(obj)


hash_ = Hashing.hash_


class _ClassPropertyMeta(type):
    """Implement `property` to a `classmethod`."""
    # TODO: in py39+ decorators `classmethod` and `property` can be combined
    @property
    def maxsize(cls):
        return cls._maxsize

    @maxsize.setter
    def maxsize(cls, value):
        if value < 0:
            raise ValueError(
                "`maxsize` should be larger than zero. "
                "To disable caching, use `Caching.disable()`.")
        cls._maxsize = value
        for func in cls._cached_functions:
            func.cache_info.maxsize = value

    @property
    def policy(cls):
        return cls._policy

    @policy.setter
    def policy(cls, value):
        if value not in cls._policies:
            raise ValueError("Cache retention policy not recognized.")
        if value == "lfu" != cls._policy:
            # Reset counter if we change policy to lfu
            # otherwise new objects are prone to being discarded immediately.
            # Now, the counter is not just used for stats,
            # it is part of the retention policy.
            for func in cls._cached_functions:
                for item in func.cache_info._caches.values():
                    item.reset()
        cls._policy = value
        for func in cls._cached_functions:
            func.cache_info.policy = value


class Caching(metaclass=_ClassPropertyMeta):
    """Infrastructure to hold cached objects.

    Caching is used for pre-computed objects that are expensive to compute.

    Attributes:
        maxsize (``int``):
            Maximum number of caches to store. If the dictionary is full, new
            caches are assigned according to the set cache retention policy.
        policy (``'fifo'``, ``'lru'``, ``'lfu'``):
            Cache retention policy.
    """
    _enabled: bool = True
    _policies: list = ['fifo', 'lru', 'lfu']
    _default_maxsize: int = 128   # class default maxsize
    _default_policy: str = 'lru'  # class default policy
    _maxsize = _default_maxsize   # user-defined maxsize
    _policy = _default_policy     # user-defined policy
    _cached_functions: list = []

    @classmethod
    def _get_key(cls, func, *args, **kwargs):
        """Calculate the hex hash from the sum of the hashes
        of the passed arguments and keyword arguments.
        """
        # get a dictionary of default parameters
        params = func.cache_info._signature.parameters
        defaults = {param: value.default for param, value in params.items()}
        # get a dictionary of the passed parameters
        passed = {**dict(zip(params, args)), **kwargs}
        # to save time hashing, discard the values equal to the default
        to_remove = [param for param, value in passed.items()
                     if value == defaults[param]]
        [passed.pop(param) for param in to_remove]
        # sum of the hash of the items (param, value)
        total_hash = sum([hash_(obj) for obj in passed.items()])
        return hex(hash_(total_hash))

    @classmethod
    def _get(cls, dic, key, policy):
        """Get the cached object container
        under the implemented caching policy.
        """
        obj = dic[key]
        if policy == "lru":
            dic.move_to_end(key)
        # update stats
        obj.increment()
        return obj

    @classmethod
    def _pop(cls, dic, policy):
        """Remove one cached item as per the implemented caching policy."""
        if policy == "lfu":
            keys = list(dic)
            idx = np.argmin([item.counter for item in dic.values()])
            dic.move_to_end(keys[idx], last=False)
        dic.pop(next(iter(dic)))

    @classmethod
    def _decorator(cls, func, maxsize, policy):
        # assign caching attributes to decorated function
        func.cache_info = CacheInfo(func, maxsize=maxsize, policy=policy)
        func.clear_cache = func.cache_info._clear_cache
        cls._cached_functions.append(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not cls._enabled:
                return func(*args, **kwargs)

            key = cls._get_key(func, *args, **kwargs)
            # shorthand access
            caches = func.cache_info._caches
            maxsize = func.cache_info.maxsize
            policy = func.cache_info.policy

            if key in caches:
                # output has been cached; update stats and return it
                out = cls._get(caches, key, policy)
                func.cache_info.misses += 1
                return out.item

            while len(caches) >= maxsize:
                # output not cached and no space available, so remove
                # items as per the caching policy until there is space
                cls._pop(caches, policy)

            # cache new entry and update stats
            out = CachedObject(func(*args, **kwargs))
            caches[key] = out
            func.cache_info.hits += 1
            func.cache_info.current_size = len(caches)
            return out.item

        return wrapper

    @classmethod
    def cache(cls, func=None, /, *, maxsize=_maxsize, policy=_policy):
        """Cache the output of the decorated function.

        Arguments:
            func (``function``):
                Function to be decorated.
            maxsize (``int`` or ``None``):
                Maximum cache size for the decorated function.
                If None, defaults to ``pyccl.Caching.maxsize``.
            policy (``'fifo'``, ``'lru'``, ``'lfu'``):
                Cache retention policy. When the storage reaches maxsize
                decide which cached object will be deleted. Default is 'lru'.\n
                'fifo': first-in-first-out,\n
                'lru': least-recently-used,\n
                'lfu': least-frequently-used.
        """
        if maxsize < 0:
            raise ValueError(
                "`maxsize` should be larger than zero. "
                "To disable caching, use `Caching.disable()`.")
        if policy not in cls._policies:
            raise ValueError("Cache retention policy not recognized.")

        if func is None:
            # `@cache` without parentheses
            return functools.partial(
                cls._decorator, maxsize=maxsize, policy=policy)
        # `@cache()` with parentheses
        return cls._decorator(func, maxsize=maxsize, policy=policy)

    @classmethod
    def enable(cls):
        cls._enabled = True

    @classmethod
    def disable(cls):
        cls._enabled = False

    @classmethod
    def toggle(cls):
        cls._enabled = not cls._enabled

    @classmethod
    def reset(cls):
        cls.maxsize = cls._default_maxsize
        cls.policy = cls._default_policy

    @classmethod
    def clear_cache(cls):
        [func.clear_cache() for func in cls._cached_functions]


cache = Caching.cache


class CacheInfo:
    """Cache info container.
    Assigned to cached function as ``function.cache_info``.

    Parameters:
        func (``function``):
            Function in which an instance of this class will be assigned.
        maxsize (``Caching.maxsize``):
            Maximum number of caches to store.
        policy (``Caching.policy``):
            Cache retention policy.

    .. note ::

        To assist in deciding an optimal ``maxsize`` and ``policy``, instances
        of this class contain the following attributes which are updated
        on every function call:
            - ``hits``: number of times the function has computed something
            - ``misses``: number of times the function has been bypassed
            - ``current_size``: current size of the cache dictionary
    """

    def __init__(self, func, maxsize=Caching.maxsize, policy=Caching.policy):
        # we store the signature of the function on import
        # as it is the most expensive operation (~30x slower)
        self._signature = signature(func)
        self._caches = OrderedDict()
        self.maxsize = maxsize
        self.policy = policy
        self.hits = self.misses = self.current_size = 0

    def __repr__(self):
        s = f"<{self.__class__.__name__}>"
        for par, val in self.__dict__.items():
            if not par.startswith("_"):
                s += f"\n\t {par} = {repr(val)}"
        return s

    def _clear_cache(self):
        self._caches = OrderedDict()
        self.hits = self.misses = self.current_size = 0


class CachedObject:
    """A cached object container.

    Attributes:
        counter (``int``):
            Number of times the cached item has been retrieved.
    """
    counter: int = 0

    def __init__(self, obj):
        self.item = obj

    def __repr__(self):
        s = f"CachedObject(counter={self.counter})"
        return s

    def increment(self):
        self.counter += 1

    def reset(self):
        self.counter = 0
