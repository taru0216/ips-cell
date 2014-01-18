# Copyright 2014 Sungho Arai.

__author__    = 'Sungho Arai'
__copyright__ = 'Copyright (c) 2014, Sungho Arai'

import copy
import logging
import re


METRICS = re.compile("(.*){(.*)}")


class Error(Exception):
  """General exception of this module."""
  pass


class SyntaxError(Error):
  """Syntax Error at parsing."""
  pass


class EvaluationError(Error):
  """Thrown when evaluation of s-expression is failed."""
  pass


class Metric:
  """A metric of OpenTSDB.
 
  This class has three instances variable. They represent a metric name,
  the value and the tags of a data point of OpenTSDB.
  
  The typical use case is as follows:
  >>> metric_a = Metric("a", 1, ["job=foo"])   
  >>> metric_b = Metric("b", 2, ["target=hoge"])   
  """

  def __init__(self, metric_name, metric_value, tags=None):
    self.name = metric_name
    self.value = metric_value
    self.tags = tags or []
 
  def __str__(self):
    return "%s{%s}" % (self.name, ",".join(self.tags))


class MetricRepository:
  """Repository of metrics.
 
  This class is a repository. It has two kinds of usage. It can store
  metrics. You can get a metric by the name of the specified metric. 
  You can also get a list of metrics which have the same metric_name.
  
  The typical use case is as follows:
  >>> metrics = MetricRepository()
  >>> metric_a_foo = Metric("a", 1, ["job=foo"])   
  >>> metric_a_bar = Metric("a", 3, ["job=bar"])   

  >>> metrics.AddMetric(metric_a_foo)  
  >>> metrics.AddMetric(metric_a_bar)  
  >>> metric_a_foo = metrics.GetMetricFromMetricName("a{job=foo}")
  >>> metric_a_foo.value
  1
  >>> len(metrics.GetMetrics("a"))
  2
  """

  def __init__(self):
    self.metric_group = {}
    self.metrics = {}

  def AddMetric(self, metric):
    self.metrics[str(metric)] = metric
    if not metric.name in self.metric_group:
      self.metric_group[metric.name] = []
    self.metric_group[metric.name].append(metric)

  def GetMetrics(self, metric_name):
    return self.metric_group[metric_name]

  def GetMetricFromMetricName(self, metric_text):
    return self.metrics[metric_text]

  def __iter__(self):
    for metric in self.metrics.itervalues():
      yield metric


class SexpListFactory:

  def GenSexpList(self, sexp_rules, metric_repo):
    """Generate S-Expression list. 

    This method generates s-expression list from the specified 
    s-expression rules and metric repository. For each rule, 
    it extracts the equivalent s-expressions which include existing
    metrics from its representative metric name in the rule.

    Representative metric name is expressed as a metric name, 
    and it specifies a set of metrics which have the same metric
    name.

    If the S-expression rule is like this:

        (setm
            (quote $disk-usage_per_disk-size)
            (/ $disk-usage $disk-size))

    and the metric repository contains the following metrics:

        disk-usage{job=test1}
        disk-usage{job=test2}
        disk-size{job=test1}
        disk-size{job=test2}

    then you would get the following S-expression list:

        [(setm
            (quote $disk-usage_per_disk-size{job=test1})
            (/ $disk-usage{job=test1} $disk-size{job=test1}),
        (setm
            (quote $disk-usage_per_disk-size{job=test2})
            (/ $disk-usage{job=test2} $disk-size{job=test2})]

    You can use this method like the following:

    >>> metrics = MetricRepository()
    >>> metrics.AddMetric(Metric("disk-usage", 1, ["job=test1"])) 
    >>> metrics.AddMetric(Metric("disk-usage", 2, ["job=test2"])) 
    >>> metrics.AddMetric(Metric("disk-size", 10, ["job=test1"])) 
    >>> metrics.AddMetric(Metric("disk-size", 20, ["job=test2"])) 
 
    >>> rule =[('(setm' 
    ...    '(quote $disk-usage_per_disk-size)'
    ...    '(/ $disk-usage $disk-size))')]
    >>> sexp_list = SexpListFactory().GenSexpList(rule, metrics)
    >>> len(sexp_list)
    2
    >>> print sexp_list[0]
    (setm (quote $disk-usage_per_disk-size{job=test1}) (/ $disk-usage{job=test1} $disk-size{job=test1}))
    >>> print sexp_list[1]
    (setm (quote $disk-usage_per_disk-size{job=test2}) (/ $disk-usage{job=test2} $disk-size{job=test2}))
    """
    sexp_list = []
    for sexp_rule in sexp_rules:
      parsed_sexp_rule = self._ParseRule(sexp_rule)
      leftmost = self._GetLeftMostMetricName(parsed_sexp_rule)

      mg = None
      try:
        mg = metric_repo.GetMetrics(leftmost)
      except KeyError:
        return []

      for metric in mg:
        tags = ",".join(metric.tags)
        sexp_list.append(
            self._CreateOpRuleWithTag(tags, copy.deepcopy(parsed_sexp_rule)))

    logging.info("%d s-expressions generated", len(sexp_list))
    for sexp in sexp_list:
      logging.debug("sexp: %s", str(sexp))
    return sexp_list

  def _CreateOpRuleWithTag(self, tags, sexp):
    if isinstance(sexp, SList):
      for sub_sexp in sexp.list_of_sexp:
        self._CreateOpRuleWithTag(tags, sub_sexp)
    elif isinstance(sexp, MetricAtom):
      sexp.value =  "%s{%s}" % (sexp.value, tags)
    return sexp

  def _ParseRule(self, calc_rule):
    """Parser of s-expression.
   
    This method parses s-expression like (setm (quote $x) 1). It returns
    SList instance that can be evaluated.
  
    >>> metrics = MetricRepository()
    >>> metrics.AddMetric(Metric("b", 3, ["job=test"])) 
    >>> metrics.AddMetric(Metric("c", 3, ["job=test"])) 
    >>> metrics.AddMetric(Metric("d", 0.1, ["job=test"])) 
    >>> env = { "metrics": metrics, 
    ...     "symtable": {
    ...     "+": Add(), 
    ...     "setm": Setm(), 
    ...     "quote": Quote()}}
    >>> rule1 ='(setm (quote $b{job=test}) 5)'
    >>> sexp = SexpListFactory()._ParseRule(rule1)
    >>> sexp.Eval(env).value
    5.0

    >>> rule1 ='(setm (quote $a{job=test}) (+ 3 7))'
    >>> sexp = SexpListFactory()._ParseRule(rule1)
    >>> sexp.Eval(env).value
    10.0
    """
    return self._Parse(self._Tokenize(calc_rule))
    
  def _Tokenize(self, rule):
    return rule.replace('(',' ( ').replace(')',' ) ').split()

  def _Parse(self, tokens):
    if len(tokens) == 0:
      raise SyntaxError('unexpected EOF while reading')
    token = tokens.pop(0)
    if '(' == token:
      expression = []
      while tokens[0] != ')':
          expression.append(self._Parse(tokens))
      tokens.pop(0) 
      return SList(expression)
    elif ')' == token:
      raise SyntaxError('unexpected )')
    else:
      try:
        return Atom(float(token))
      except ValueError:
        pass
      if token.find('"') == 0:
        return Atom(token[1:-1])
      if token.find("$") == 0:
        return MetricAtom(token[1:])
      return Symbol(token)

  def _GetLeftMostMetricName(self, expression):
    """ Get the left most metric to extract tags

    >>> sexp = SList([
    ...     Symbol("setm"), 
    ...     SList([Symbol("quote"), MetricAtom("b")]),
    ...     SList([Symbol("+"), MetricAtom("c"), Atom("5")])])
    >>> left = SexpListFactory()._GetLeftMostMetricName(sexp)
    >>> left
    'c'

    >>> sexp = SList([
    ...     Symbol("setm"), 
    ...     SList([Symbol("quote"), MetricAtom("b")]), 
    ...     MetricAtom("c")])
    >>> left = SexpListFactory()._GetLeftMostMetricName(sexp)
    >>> left
    'c'
    """
    if (isinstance(expression, SList) and 
        expression.list_of_sexp[0].value == "setm"):
      return self._GetLeftMostMetricName(expression.list_of_sexp[2])
    elif isinstance(expression, SList):
      for sexp in expression.list_of_sexp:
        leftmost =  self._GetLeftMostMetricName(sexp)
        if leftmost:
          return leftmost
    elif isinstance(expression, MetricAtom):
      return expression.value 
    else:
      return None


class Sexp:
  """S-Expression

  >>> metrics = MetricRepository()
  >>> metrics.AddMetric(Metric("b", 3, ["job=test"])) 
  >>> metrics.AddMetric(Metric("c", 3, ["job=test"])) 
  >>> metrics.AddMetric(Metric("d", 0.1, ["job=test"])) 

  >>> env = { 
  ...     "metrics" : metrics, 
  ...     "symtable": {"+": Add(), "setm": Setm(), "quote": Quote()}}
  >>> sexp = SList([Symbol("+"), Atom(1), Atom(1)])
  >>> sexp.Eval(env).value
  2

  >>> sexp = SList([
  ...     Symbol("setm"), 
  ...     SList([Symbol("quote"), MetricAtom("b{job=test}")]), 
  ...     Atom(1)])
  >>> sexp.Eval(env).value
  1

  >>> sexp = SList([
  ...     Symbol("setm"), 
  ...     SList([Symbol("quote"), MetricAtom("b{job=test}")]), 
  ...     SList([Symbol("+"), Atom(3), Atom(5)])])
  >>> sexp.Eval(env).value
  8
  """

  def Eval(self, env):
    return self


class Atom(Sexp):

  def __init__(self, value):
    self.value = value

  def __str__(self):
    if isinstance(self.value, str):
      return '"%s"' % self.value
    else:
      return str(self.value)


class SList(Sexp):

  def __init__(self, list_of_sexp):
    self.list_of_sexp = list_of_sexp

  def Eval(self, env):

    car = self.list_of_sexp[0].Eval(env)
    if isinstance(car, Func):
      args = []
      for s in self.list_of_sexp[1:]:
        args.append(s.Eval(env))
      return car.Call(args, env)
    elif isinstance(car, Quote):
      if len(self.list_of_sexp[1:]) == 1:
        return self.list_of_sexp[1]
      return SList(self.list_of_sexp[1:])

  def __str__(self):
    return "(%s)" % " ".join([str(v) for v in self.list_of_sexp])


class Nil(Sexp):

  def __str__(self):
    return "nil" 


class Func(Sexp):

  def Call(self, args, env):
    pass


class Add(Func):

  def Call(self, args, env):
    result = 0 
    for arg in args:
      result += arg.value
    return Atom(result)


class Subtract(Func):

  def Call(self, args, env):
    result = args[0].value
    for arg in args[1:]:
      result -= arg.value
    return Atom(result)


class Multiple(Func):

  def Call(self, args, env):
    result = 1
    for arg in args:
      result *= arg.value
    return Atom(result)


class Divide(Func):

  def Call(self, args, env):
    try:
      result = float(args[0].value)
      for arg in args[1:]:
        result /= arg.value
    except ZeroDivisionError:
      logging.warning("Division by Zero")
    return Atom(result)


class Quote(Sexp):
  pass
  

class Setm(Func):

  def Call(self, args, env):
    try:
      env["metrics"].GetMetricFromMetricName(args[0].value).value = args[1].value
    except KeyError:
      matched_metric = METRICS.search(args[0].value)
      metric_name = matched_metric.group(1)
      tags = matched_metric.group(2)
      env["metrics"].AddMetric(Metric(
          metric_name,
          args[1].value, 
          tags.split(",")))
      logging.debug(
          "Metric is created at Setm: new metric:%s tags:%s",
           metric_name,
           tags.split(","))
    return args[1]


class Symbol(Atom):

  def Eval(self, env):
    try:
      value =  env["symtable"][self.value]
    except KeyError:
      logging.warning("KeyError at Eval() of Symbol class: %s", self.value)
      raise EvaluationError()
    return value

  def __str__(self):
    return self.value


class MetricAtom(Atom):
  def Eval(self, env):
    try:
      return Atom(env["metrics"].GetMetricFromMetricName(self.value).value)
    except KeyError:
      return self

  def __str__(self):
    return "$%s" % self.value  


class MetricEvaluator:
  """Metric Evaluator

  This class evaluates the specified list of s-expressions
  such as (+ 3 5) and (setm $c (- $e $f)) with the specified
  metrics under the one-time environment.

  A list of s-expressions is list of instances of Sexp class.

  >>> sexp1 = SList([
  ...     Symbol("setm"), 
  ...     SList([Symbol("quote"), MetricAtom("b{job=test}")]),
  ...     SList([Symbol("+"), MetricAtom("a{job=test}"), Atom(5)])])

  >>> sexp2 = SList([
  ...     Symbol("setm"), 
  ...     SList([Symbol("quote"), MetricAtom("c{job=test}")]),
  ...     SList([Symbol("+"), MetricAtom("b{job=test}"), Atom(5)])])

  >>> sexp3 = SList([
  ...     Symbol("setm"), 
  ...     SList([Symbol("quote"), MetricAtom("d{job=test}")]),
  ...     SList([Symbol("+"), MetricAtom("a{job=test}"), Atom(5)])])

  >>> sexp4 = SList([
  ...     Symbol("setm"), 
  ...     SList([Symbol("quote"), MetricAtom("e{job=test}")]),
  ...     SList([Symbol("+"), MetricAtom("d{job=test}"), Atom(5)])])

  >>> sexp_list1 = [sexp1, sexp2]
  >>> sexp_list2 = [sexp3]
  >>> sexp_list3 = [sexp4]

  Metrics are like this:

  >>> metrics = MetricRepository()
  >>> metrics.AddMetric(Metric("a", 3, ["job=test"])) 

  and MetricEvaluator evaluates s-expression like this:

  >>> calc = MetricEvaluator()

  so under the one-time environment, you can evaluate sexp_list1.

  >>> calc.Eval(sexp_list1, metrics)
  >>> metrics.GetMetricFromMetricName("c{job=test}").value
  13

  But you fail to evaluate the following lists 
  under the one-time environment: 

  >>> calc.Eval(sexp_list2, metrics)
  >>> metrics.GetMetricFromMetricName("d{job=test}").value
  8
  >>> calc.Eval(sexp_list3, metrics)
  >>> metrics.GetMetricFromMetricName("e{job=test}").value
  13
  """

  SYMTABLE = {
    "+": Add(), 
    "-": Subtract(), 
    "*": Multiple(), 
    "/": Divide(), 
    "setm": Setm(), 
    "quote": Quote(), 
  }

  def Eval(self, sexp_list, metrics):
    env = { 
        "metrics": metrics, 
        "symtable": MetricEvaluator.SYMTABLE }

    for sexp in sexp_list:
      try:
        sexp.Eval(env)
      except EvaluationError, e:
        logging.warning("Failed to evaluate s-expression: %s", e)


if __name__ == "__main__":
  import doctest
  doctest.testmod()
