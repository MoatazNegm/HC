#!/bin/sh
# iscsichap.sh <target iqn> <chapuser> <chappas token> [<initiator iqn> ...]
# QSD5.341 (test 653 QX-054): CHAP of the node ACLs of <target>/tpg1, then the TPG's authentication attribute.
#   chappas token chapenc_<encrypted>  the CHAP user and secret are set on the ACL of each initiator given
#                 clearchap            the CHAP of those ACLs is removed
#                 anything else        (nochap: a LUN without CHAP; a record from before QSD5.341) the ACLs are left as they are
# authentication=1 when an ACL of the TPG has a CHAP user (LIO then refuses a login without CHAP or with a wrong secret on
# every ACL of this portal), 0 when none has. Before, the pair was set on the TPG only (used by generated ACLs, which are
# off) with authentication=0, so CHAP was never asked.
# The secret is decrypted here only (encthis.sh/decthis.sh, as the CIFS domain password) and written with the shell's
# printf into configfs: it is on no command line, so not in ~/.targetcli/log.txt, ps or a trace. targetcli saveconfig keeps
# it in /etc/target/saveconfig.json (root only), which LIO needs to restore the ACL.
T=$1
chapuser=$2
chaptoken=$3
[ -n "$T" ] || exit 1
shift 3 2>/dev/null
cfs=/sys/kernel/config/target/iscsi/$T/tpgt_1
[ -d $cfs ] || { echo "iscsichap: no target $T"; exit 1; }
nolun='This_lun_is_not_mapped'
case "$chaptoken" in
 chapenc_*)
  enc=`echo "$chaptoken" | sed 's/^chapenc_//; s/@@sep/\//g'`
  secret=`/TopStor/decthis.sh "$chapuser" "$enc" 2>/dev/null | sed -n 's/^_result\(.*\)_result$/\1/p'`
  # the rules fapi checked (12-16 characters); anything else is a broken record: nothing is set, and the secret is not shown
  if ! echo "$chapuser" | grep -Eq '^[A-Za-z0-9._:-]{1,64}$' || ! printf '%s' "$secret" | grep -Eq '^[A-Za-z0-9._:@!-]{12,16}$';
  then
   echo "iscsichap: the CHAP of $T cannot be read, not set"
   secret=''
   mode=keep
  else
   mode=set
  fi
  ;;
 clearchap) mode=clear ;;
 *) mode=keep ;;
esac
if [ $mode != keep ];
then
 for i in "$@"
 do
  [ "$i" = "$nolun" ] && continue
  acl=`echo $i | tr 'A-Z' 'a-z'`
  [ -d $cfs/acls/$acl/auth ] || continue
  if [ $mode = set ];
  then
   printf '%s' "$chapuser" > $cfs/acls/$acl/auth/userid
   printf '%s' "$secret" > $cfs/acls/$acl/auth/password
   echo "iscsichap: CHAP user $chapuser set on $T acl $acl"
  else
   printf 'NULL' > $cfs/acls/$acl/auth/userid
   printf 'NULL' > $cfs/acls/$acl/auth/password
   echo "iscsichap: CHAP removed from $T acl $acl"
  fi
 done
fi
secret=''
auth=0
for d in $cfs/acls/*/auth
do
 [ -f $d/userid ] || continue
 uid=`cat $d/userid 2>/dev/null`
 [ -n "$uid" -a "$uid" != NULL ] && auth=1
done
cur=`cat $cfs/attrib/authentication 2>/dev/null`
[ "$cur" = "$auth" ] || targetcli /iscsi/$T/tpg1 set attribute authentication=$auth
echo "iscsichap: $T authentication=$auth"
