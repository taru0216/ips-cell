#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.50])
AC_INIT(ips-cell, 14.01.1390036067, [taru0216@gmail.com])
AM_INIT_AUTOMAKE([-Wno-portability])

# Checks for programs.
AC_PROG_INSTALL
AC_PROG_MAKE_SET

# Checks for python 
AC_PATH_PROGS([PYTHON], [python2.7 python2.6 python2 python])

AC_MSG_CHECKING([python version])
PYTHON_VERSION="$($PYTHON -V 2>&1 | cut -d' ' -f2)"

v=$(echo $(echo $(echo $PYTHON_VERSION | cut -d. -f1,2) \* 10 | bc) | cut -d. -f1)
if test "$v" -ge "26"; then
  AC_MSG_RESULT($PYTHON_VERSION)
else
  AC_MSG_ERROR([requires at least 2.6: $PYTHON_VERSION])
fi

# Checks for libraries.

# Checks for header files.

# Checks for typedefs, structures, and compiler characteristics.

# Checks for library functions.

AC_CONFIG_FILES([Makefile
                 examples/Makefile])
AC_OUTPUT
