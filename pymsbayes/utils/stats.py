#! /usr/bin/env python

import sys
import os
import math
from cStringIO import StringIO

from pymsbayes.utils.messaging import get_logger

_LOG = get_logger(__name__)

class SampleSummarizer(object):
    def __init__(self, name='sample summarizer'):
        self.name = name
        self._min = None
        self._max = None
        self._n = 0
        self._sum = 0
        self._sum_of_squares = 0
    
    def add_sample(self, x):
        self._n += 1
        self._sum += x
        self._sum_of_squares += x*x
        if not self._min:
            self._min = x
        elif x < self._min:
            self._min = x
        if not self._max:
            self._max = x
        elif x > self._max:
            self._max = x

    def update_samples(self, x_iter):
        for x in x_iter:
            self.add_sample(x)

    def _get_n(self):
        return self._n
    
    n = property(_get_n)

    def _get_min(self):
        return self._min

    def _get_max(self):
        return self._max

    minimum = property(_get_min)
    maximum = property(_get_max)
    
    def _get_mean(self):
        if self._n < 1:
            return None
        return float(self._sum)/self._n
    
    def _get_variance(self):
        if self._n < 1:
            return None
        if self._n == 1:
            return float('inf')
        return (self._sum_of_squares - (self._get_mean()*self._sum))/(self._n-1)

    def _get_std_dev(self):
        if self._n < 1:
            return None
        return math.sqrt(self._get_variance())

    def _get_pop_variance(self):
        if self._n < 1:
            return None
        return (self._sum_of_squares - (self._get_mean()*self._sum))/self._n

    mean = property(_get_mean)
    variance = property(_get_variance)
    pop_variance = property(_get_pop_variance)
    std_deviation = property(_get_std_dev)

    def __str__(self):
        s = StringIO()
        s.write('name = {0}\n'.format(self.name))
        s.write('sample size = {0}\n'.format(self._n))
        s.write('sum = {0}\n'.format(self._sum))
        s.write('sum of squares = {0}\n'.format(self._sum_of_squares))
        s.write('min = {0}\nmax = {1}\n'.format(self._min, self._max))
        s.write('mean = {0}\n'.format(self.mean))
        s.write('variance = {0}\n'.format(self.variance))
        s.write('pop variance = {0}\n'.format(self.pop_variance))
        return s.getvalue()


