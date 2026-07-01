#!/bin/sh

midleo_load_zos_env() {
  if [ -z "${MWAGTDIR:-}" ]; then
    echo "MWAGTDIR is not set"
    return 1
  fi

  if [ -z "${HOMEDIR:-}" ]; then
    HOMEDIR="$MWAGTDIR/config"
  fi

  if [ ! -f "$HOMEDIR/mwagent.config" ]; then
    echo "no mwagent.config file found"
    return 1
  fi

  . "$HOMEDIR/mwagent.config"

  if [ -z "${PYTHON:-}" ]; then
    echo "PYTHON not set"
    return 1
  fi

  if [ -n "${ZOS_PYTHON_HOME:-}" ] && [ -d "$ZOS_PYTHON_HOME/bin" ]; then
    PATH="$ZOS_PYTHON_HOME/bin:$PATH"
    LIBPATH="$ZOS_PYTHON_HOME/lib${LIBPATH:+:$LIBPATH}"
  fi

  if [ -n "${ZOS_ZPYMQI_PATH:-}" ]; then
    PYTHONPATH="$ZOS_ZPYMQI_PATH${PYTHONPATH:+:$PYTHONPATH}"
  fi

  if [ -n "${ZOS_STEPLIB:-}" ]; then
    STEPLIB="$ZOS_STEPLIB${STEPLIB:+:$STEPLIB}"
  fi

  if [ -n "${ZOAU_HOME:-}" ]; then
    PATH="$ZOAU_HOME/bin:$PATH"
    LIBPATH="$ZOAU_HOME/lib${LIBPATH:+:$LIBPATH}"
    PYTHONPATH="$ZOAU_HOME/lib${PYTHONPATH:+:$PYTHONPATH}"
  fi

  MIDLEO_CRYPTO_SECRET="${MIDLEO_CRYPTO_SECRET:-$HOMEDIR/crypto.secret}"
  MIDLEO_SHELL="${MIDLEO_SHELL:-/bin/sh}"
  _BPXK_AUTOCVT="${ZOS_BPXK_AUTOCVT:-ON}"
  _CEE_RUNOPTS="${ZOS_CEE_RUNOPTS:-FILETAG(AUTOCVT,AUTOTAG) POSIX(ON)}"
  _TAG_REDIR_ERR="${ZOS_TAG_REDIR_ERR:-txt}"
  _TAG_REDIR_IN="${ZOS_TAG_REDIR_IN:-txt}"
  _TAG_REDIR_OUT="${ZOS_TAG_REDIR_OUT:-txt}"

  export AMQSEVT
  export ACEUSR
  export DSPMQ
  export DSPMQVER
  export IIBMQSIPROFILE
  export JOB_TIMEOUT_SECONDS
  export LIBPATH
  export MIDLEO_CRYPTO_SECRET
  export MIDLEO_SHELL
  export MQSIPROFILE
  export MWAGTDIR
  export PATH
  export PYTHON
  export PYTHONPATH
  export RUNMQSC
  export STEPLIB
  export ZOAU_HOME
  export _BPXK_AUTOCVT
  export _CEE_RUNOPTS
  export _TAG_REDIR_ERR
  export _TAG_REDIR_IN
  export _TAG_REDIR_OUT
}
