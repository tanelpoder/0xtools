#============================================================================
# Title       : psn.bash
# Description : bash_completion file for process snapper
# Author      : Bart Sjerps <bart@outrun.nl>
# Usage       : Copy this file to /etc/bash_completion.d/
# License     : GPLv3+
# ---------------------------------------------------------------------------

_psn() {
  local -a opts shortopts longopts
  local cur prev disks
  _get_comp_words_by_ref cur prev

  shortopts=(h d p t r a o i s g G)
  longopts+=(pid thread recursive all-states sample-hz ps-hz output-sample-db input-sample-db list)
  
  opts=$(printf "\x2d%s " "${shortopts[@]}")
  opts+=$(printf "\x2d\x2d%s " "${longopts[@]}")

  case ${prev} in
    psn)                   COMPREPLY=($(compgen -W "$opts" -- ${cur})) ;;
    -h)                    ;;
    -d)                    COMPREPLY=($(compgen -W "2 5 10" -- ${cur})) ;;
    -p|--pid)              COMPREPLY=($(compgen -W "$(ps -eo comm)" -- ${cur})) ;;
    -t)                    ;;
    --list)                ;;
    -r|--recursive)        COMPREPLY=($(compgen -W "$opts" -- ${cur})) ;;
    -a|--all-states)       COMPREPLY=($(compgen -W "$opts" -- ${cur})) ;;
       --sample-hz)        ;;
       --ps-hz)            ;;
    -o|--output-sample-db) COMPREPLY=($(compgen -f -- ${cur})) ;;
    -i|--input-sample-db)  COMPREPLY=($(compgen -f -- ${cur})) ;;
    -s|-g|-G)              COMPREPLY=($(compgen -W "$(psn --list | awk 'NF==2 {print $1}')" -- ${cur})) ;;
    *)                     COMPREPLY=($(compgen -W "$opts" -- ${cur})) ;;
  esac
  return 0
}
complete -F _psn psn
