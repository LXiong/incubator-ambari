#!/usr/bin/env python2.6

'''
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''

import optparse
from pprint import pprint
import shlex
import sys
import os
import signal
import subprocess
import re
import string
import glob
import platform
import shutil
import stat
import fileinput
import urllib2
import time
import getpass
import socket
import datetime
import socket
import tempfile
import random
import pwd

# debug settings
VERBOSE = False
SILENT = False
SERVER_START_DEBUG = False

# action commands
SETUP_ACTION = "setup"
START_ACTION = "start"
STOP_ACTION = "stop"
RESET_ACTION = "reset"
UPGRADE_ACTION = "upgrade"
UPGRADE_STACK_ACTION = "upgradestack"
UPDATE_METAINFO_ACTION = "update-metainfo"
STATUS_ACTION = "status"
SETUP_HTTPS_ACTION = "setup-https"
LDAP_SETUP_ACTION = "setup-ldap"
SETUP_GANGLIA_HTTPS_ACTION = "setup-ganglia-https"
SETUP_NAGIOS_HTTPS_ACTION  = "setup-nagios-https"
ENCRYPT_PASSWORDS_ACTION = "encrypt-passwords"

ACTION_REQUIRE_RESTART = [RESET_ACTION, UPGRADE_ACTION, UPGRADE_STACK_ACTION, SETUP_HTTPS_ACTION, LDAP_SETUP_ACTION]

# selinux commands
GET_SE_LINUX_ST_CMD = "/usr/sbin/sestatus"
SE_SETENFORCE_CMD = "setenforce 0"
SE_STATUS_DISABLED = "disabled"
SE_STATUS_ENABLED = "enabled"
SE_MODE_ENFORCING = "enforcing"
SE_MODE_PERMISSIVE = "permissive"

# iptables commands
IP_TBLS_ST_CMD = "/sbin/service iptables status"
IP_TBLS_STOP_CMD = "/sbin/service iptables stop"
IP_TBLS_ENABLED = "Firewall is running"
IP_TBLS_DISABLED = "Firewall is stopped.\n"
IP_TBLS_SRVC_NT_FND = "iptables: unrecognized service"

# server commands
ambari_provider_module_option = ""
ambari_provider_module = os.environ.get('AMBARI_PROVIDER_MODULE')

# Non-root user setup commands
NR_USER_PROPERTY = "ambari-server.user"
NR_USER_COMMENT =  "Ambari user"
NR_GET_OWNER_CMD = 'stat -c "%U" {0}'
NR_USERADD_CMD = 'useradd -M --comment "{1}" ' \
                 '--shell /sbin/nologin -d /var/lib/ambari-server/keys/ {0}'
NR_SET_USER_COMMENT_CMD = 'usermod -c "{0}" {1}'
NR_CHMOD_CMD = 'chmod {0} {1} {2}'
NR_CHOWN_CMD = 'chown {0} {1} {2}'

RECURSIVE_RM_CMD = 'rm -rf {0}'

SSL_PASSWORD_FILE = "pass.txt"
SSL_PASSIN_FILE = "passin.txt" 

# openssl command
VALIDATE_KEYSTORE_CMD = "openssl pkcs12 -info -in '{0}' -password file:'{1}' -passout file:'{2}'"
EXPRT_KSTR_CMD = "openssl pkcs12 -export -in '{0}' -inkey '{1}' -certfile '{0}' -out '{4}' -password file:'{2}' -passin file:'{3}'"
CHANGE_KEY_PWD_CND = 'openssl rsa -in {0} -des3 -out {0}.secured -passout pass:{1}'
GET_CRT_INFO_CMD = 'openssl x509 -dates -subject -in {0}'

#keytool commands
KEYTOOL_IMPORT_CERT_CMD="{0}" + os.sep + "bin" + os.sep + "keytool -import -alias '{1}' -storetype '{2}' -file '{3}' -storepass '{4}' -noprompt"
KEYTOOL_DELETE_CERT_CMD="{0}" + os.sep + "bin" + os.sep + "keytool -delete -alias '{1}' -storepass '{2}' -noprompt"
KEYTOOL_KEYSTORE=" -keystore '{0}'"

# constants
STACK_NAME_VER_SEP = "-"
JAVA_SHARE_PATH="/usr/share/java"
SERVER_OUT_FILE="/var/log/ambari-server/ambari-server.out"
SERVER_LOG_FILE="/var/log/ambari-server/ambari-server.log"
BLIND_PASSWORD="*****"

# terminal styles
BOLD_ON='\033[1m'
BOLD_OFF='\033[0m'

#Common messages
PRESS_ENTER_MSG="Press <enter> to continue."

#SSL certificate metainfo
COMMON_NAME_ATTR='CN'
NOT_BEFORE_ATTR='notBefore'
NOT_AFTER_ATTR='notAfter'

if ambari_provider_module is not None:
  ambari_provider_module_option = "-Dprovider.module.class=" +\
                                  ambari_provider_module + " "

SERVER_START_CMD="{0}" + os.sep + "bin" + os.sep +\
                 "java -server -XX:NewRatio=3 "\
                 "-XX:+UseConcMarkSweepGC " +\
                 "-XX:-UseGCOverheadLimit -XX:CMSInitiatingOccupancyFraction=60 " +\
                 ambari_provider_module_option +\
                 os.getenv('AMBARI_JVM_ARGS','-Xms512m -Xmx2048m') +\
                 " -cp {1}"+ os.pathsep + "{2}" +\
                 " org.apache.ambari.server.controller.AmbariServer "\
                 ">" + SERVER_OUT_FILE + " 2>&1 &" \
                 " echo $! > {3}" # Writing pidfile
SERVER_START_CMD_DEBUG="{0}" + os.sep + "bin" + os.sep +\
                       "java -server -XX:NewRatio=2 -XX:+UseConcMarkSweepGC " +\
                       ambari_provider_module_option +\
                       os.getenv('AMBARI_JVM_ARGS','-Xms512m -Xmx2048m') +\
                       " -Xdebug -Xrunjdwp:transport=dt_socket,address=5005,"\
                       "server=y,suspend=n -cp {1}"+ os.pathsep + "{2}" +\
                       " org.apache.ambari.server.controller.AmbariServer &" \
                       " echo $! > {3}" # Writing pidfile

SECURITY_PROVIDER_GET_CMD="{0}" + os.sep + "bin" + os.sep + "java -cp {1}" +\
                          os.pathsep + "{2} " +\
                          "org.apache.ambari.server.security.encryption" +\
                          ".CredentialProvider GET {3} {4} {5} " +\
                          "> " + SERVER_OUT_FILE + " 2>&1"

SECURITY_PROVIDER_PUT_CMD="{0}" + os.sep + "bin" + os.sep + "java -cp {1}" +\
                          os.pathsep + "{2} " +\
                          "org.apache.ambari.server.security.encryption" +\
                          ".CredentialProvider PUT {3} {4} {5} " +\
                          "> " + SERVER_OUT_FILE + " 2>&1"

SECURITY_PROVIDER_KEY_CMD="{0}" + os.sep + "bin" + os.sep + "java -cp {1}" +\
                          os.pathsep + "{2} " +\
                          "org.apache.ambari.server.security.encryption" +\
                          ".MasterKeyServiceImpl {3} {4} {5} " +\
                          "> " + SERVER_OUT_FILE + " 2>&1"

SECURITY_KEYS_DIR = "security.server.keys_dir"
SECURITY_MASTER_KEY_LOCATION = "security.master.key.location"
SECURITY_KEY_IS_PERSISTED = "security.master.key.ispersisted"
SECURITY_KEY_ENV_VAR_NAME = "AMBARI_SECURITY_MASTER_KEY"
SECURITY_MASTER_KEY_FILENAME = "master"
SECURITY_IS_ENCRYPTION_ENABLED = "security.passwords.encryption.enabled"

SSL_KEY_DIR = 'security.server.keys_dir'
SSL_API_PORT = 'client.api.ssl.port'
SSL_API = 'api.ssl'
SSL_SERVER_CERT_NAME = 'client.api.ssl.cert_name'
SSL_SERVER_KEY_NAME = 'client.api.ssl.key_name'
SSL_CERT_FILE_NAME = "https.crt"
SSL_KEY_FILE_NAME = "https.key"
SSL_KEYSTORE_FILE_NAME = "https.keystore.p12"
SSL_KEY_PASSWORD_FILE_NAME = "https.pass.txt"
SSL_KEY_PASSWORD_LENGTH = 50
DEFAULT_SSL_API_PORT = 8443
SSL_DATE_FORMAT = '%b  %d %H:%M:%S %Y GMT'

GANGLIA_HTTPS = 'ganglia.https'
NAGIOS_HTTPS  = 'nagios.https'

JDBC_RCA_PASSWORD_ALIAS = "ambari.db.password"
CLIENT_SECURITY_KEY = "client.security"

LDAP_MGR_PASSWORD_ALIAS = "ambari.ldap.manager.password"
LDAP_MGR_PASSWORD_PROPERTY = "authentication.ldap.managerPassword"
LDAP_MGR_USERNAME_PROPERTY = "authentication.ldap.managerDn"

SSL_TRUSTSTORE_PASSWORD_ALIAS="ambari.ssl.trustStore.password"
SSL_TRUSTSTORE_PATH_PROPERTY = "ssl.trustStore.path"
SSL_TRUSTSTORE_PASSWORD_PROPERTY = "ssl.trustStore.password"
SSL_TRUSTSTORE_TYPE_PROPERTY = "ssl.trustStore.type"

AMBARI_CONF_VAR="AMBARI_CONF_DIR"
AMBARI_SERVER_LIB="AMBARI_SERVER_LIB"
JAVA_HOME="JAVA_HOME"
PID_DIR="/var/run/ambari-server"
BOOTSTRAP_DIR_PROPERTY="bootstrap.dir"
PID_NAME="ambari-server.pid"
AMBARI_PROPERTIES_FILE="ambari.properties"
AMBARI_PROPERTIES_RPMSAVE_FILE="ambari.properties.rpmsave"
RESOURCES_DIR_PROPERTY="resources.dir"

SETUP_DB_CMD = ['su', '-', 'postgres',
        '--command=psql -f {0} -v username=\'"{1}"\' -v password="\'{2}\'" -v dbname="{3}"']
UPGRADE_STACK_CMD = ['su', 'postgres',
        '--command=psql -f {0} -v stack_name="\'{1}\'"  -v stack_version="\'{2}\'" -v dbname="{3}']
UPDATE_METAINFO_CMD = 'curl -X PUT "http://{0}:{1}/api/v1/stacks2" -u "{2}":"{3}"'
PG_ST_CMD = "/sbin/service postgresql status"
PG_INITDB_CMD = "/sbin/service postgresql initdb"
PG_START_CMD = "/sbin/service postgresql start"
PG_RESTART_CMD = "/sbin/service postgresql restart"
PG_STATUS_RUNNING = "running"
PG_HBA_DIR = "/var/lib/pgsql/data/"
PG_HBA_CONF_FILE = PG_HBA_DIR + "pg_hba.conf"
PG_HBA_CONF_FILE_BACKUP = PG_HBA_DIR + "pg_hba_bak.conf.old"
POSTGRESQL_CONF_FILE = PG_HBA_DIR + "postgresql.conf"
PG_HBA_RELOAD_CMD = "su postgres --command='pg_ctl -D {0} reload'"
PG_DEFAULT_PASSWORD = "bigdata"

JDBC_DATABASE_PROPERTY = "server.jdbc.database"
JDBC_HOSTNAME_PROPERTY = "server.jdbc.hostname"
JDBC_PORT_PROPERTY = "server.jdbc.port"
JDBC_SCHEMA_PROPERTY = "server.jdbc.schema"

JDBC_USER_NAME_PROPERTY = "server.jdbc.user.name"
JDBC_PASSWORD_PROPERTY = "server.jdbc.user.passwd"
JDBC_PASSWORD_FILENAME = "password.dat"
JDBC_RCA_PASSWORD_FILENAME = "rca_password.dat"

CLIENT_API_PORT_PROPERTY = "client.api.port"
CLIENT_API_PORT = "8080"

SRVR_TWO_WAY_SSL_PORT_PROPERTY = "security.server.two_way_ssl.port"
SRVR_TWO_WAY_SSL_PORT = "8441"

SRVR_ONE_WAY_SSL_PORT_PROPERTY = "security.server.one_way_ssl.port"
SRVR_ONE_WAY_SSL_PORT = "8440"

PERSISTENCE_TYPE_PROPERTY = "server.persistence.type"
JDBC_DRIVER_PROPERTY = "server.jdbc.driver"
JDBC_URL_PROPERTY = "server.jdbc.url"

JDBC_RCA_DATABASE_PROPERTY = "server.jdbc.database"
JDBC_RCA_HOSTNAME_PROPERTY = "server.jdbc.hostname"
JDBC_RCA_PORT_PROPERTY = "server.jdbc.port"
JDBC_RCA_SCHEMA_PROPERTY = "server.jdbc.schema"

JDBC_RCA_DRIVER_PROPERTY = "server.jdbc.rca.driver"
JDBC_RCA_URL_PROPERTY = "server.jdbc.rca.url"
JDBC_RCA_USER_NAME_PROPERTY = "server.jdbc.rca.user.name"
JDBC_RCA_PASSWORD_FILE_PROPERTY = "server.jdbc.rca.user.passwd"

CHECK_COMMAND_EXIST_CMD = "type {0}"

DATABASE_INDEX = 0
PROMPT_DATABASE_OPTIONS = False
USERNAME_PATTERN = "^[a-zA-Z_][a-zA-Z0-9_\-]*$"
PASSWORD_PATTERN = "^[a-zA-Z0-9_-]*$"
DATABASE_NAMES =["postgres", "oracle"]
DATABASE_STORAGE_NAMES =["Database","Service","Schema"]
DATABASE_PORTS =["5432", "1521", "3306"]
DATABASE_DRIVER_NAMES = ["org.postgresql.Driver", "oracle.jdbc.driver.OracleDriver", "com.mysql.jdbc.Driver"]
DATABASE_CONNECTION_STRINGS = [
                  "jdbc:postgresql://{0}:{1}/{2}",
                  "jdbc:oracle:thin:@{0}:{1}/{2}",
                  "jdbc:mysql://{0}:{1}/{2}"]
DATABASE_CONNECTION_STRINGS_ALT = [
                  "jdbc:postgresql://{0}:{1}/{2}",
                  "jdbc:oracle:thin:@{0}:{1}:{2}",
                  "jdbc:mysql://{0}:{1}/{2}"]
DATABASE_CLI_TOOLS = [["psql"], ["sqlplus", "sqlplus64"], ["mysql"]]
DATABASE_CLI_TOOLS_DESC = ["psql", "sqlplus", "mysql"]
DATABASE_CLI_TOOLS_USAGE = ['su -postgres --command=psql -f {0} -v username=\'"{1}"\' -v password="\'{2}\'"',
                            'sqlplus {1}/{2} < {0} ',
                            'mysql --user={1} --password={2} {3}<{0}']

DATABASE_INIT_SCRIPTS = ['/var/lib/ambari-server/resources/Ambari-DDL-Postgres-REMOTE-CREATE.sql',
                         '/var/lib/ambari-server/resources/Ambari-DDL-Oracle-CREATE.sql',
                         '/var/lib/ambari-server/resources/Ambari-DDL-MySQL-CREATE.sql']
DATABASE_DROP_SCRIPTS = ['/var/lib/ambari-server/resources/Ambari-DDL-Postgres-REMOTE-DROP.sql',
                         '/var/lib/ambari-server/resources/Ambari-DDL-Oracle-DROP.sql',
                         '/var/lib/ambari-server/resources/Ambari-DDL-MySQL-DROP.sql']

JDBC_PROPERTIES_PREFIX = "server.jdbc.properties."
DATABASE_JDBC_PROPERTIES = [
                         [ ],
                         [
                           ["oracle.net.CONNECT_TIMEOUT", "2000"], # socket level timeout
                           ["oracle.net.READ_TIMEOUT", "2000"], # socket level timeout
                           ["oracle.jdbc.ReadTimeout", "8000"] # query fetch timeout
                         ],
                         [ ]
                        ]

REGEX_IP_ADDRESS = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
REGEX_HOSTNAME = "^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$"
REGEX_HOSTNAME_PORT = "^(.*:[0-9]{1,5}$)"
REGEX_TRUE_FALSE = "^(true|false)?$"
REGEX_ANYTHING = ".*"

POSTGRES_EXEC_ARGS = "-h {0} -p {1} -d {2} -U {3} -f {4} -v username='\"{3}\"'"
ORACLE_EXEC_ARGS = "-S '{0}/{1}@(description=(address=(protocol=TCP)(host={2})(port={3}))(connect_data=(sid={4})))' @{5} {0}"
MYSQL_EXEC_ARGS = "--host={0} --port={1} --user={2} --password={3} {4} " \
                 "-e\"set @schema=\'{4}\'; set @username=\'{2}\'; source {5};\""

JDBC_PATTERNS = {"oracle":"*ojdbc*.jar", "mysql":"*mysql*.jar"}
DATABASE_FULL_NAMES = {"oracle":"Oracle", "mysql":"MySQL", "postgres":"PostgreSQL"}
ORACLE_DB_ID_TYPES = ["Service Name", "SID"]


# jdk commands
JDK_LOCAL_FILENAME = "jdk-6u31-linux-x64.bin"
JDK_MIN_FILESIZE = 5000
JDK_INSTALL_DIR = "/usr/jdk64"
CREATE_JDK_DIR_CMD = "/bin/mkdir -p " + JDK_INSTALL_DIR
MAKE_FILE_EXECUTABLE_CMD = "chmod a+x {0}"
JAVA_HOME_PROPERTY = "java.home"
JDK_URL_PROPERTY='jdk.url'
JCE_URL_PROPERTY='jce_policy.url'
OS_TYPE_PROPERTY = "server.os_type"
GET_FQDN_SERVICE_URL="server.fqdn.service.url"

JDK_DOWNLOAD_CMD = "curl --create-dirs -o {0} {1}"
JDK_DOWNLOAD_SIZE_CMD = "curl -I {0}"

#JCE Policy files
JCE_POLICY_FILENAME = "jce_policy-6.zip"
JCE_DOWNLOAD_CMD = "curl -o {0} {1}"
JCE_MIN_FILESIZE = 5000

#Apache License Header
ASF_LICENSE_HEADER = '''
# Copyright 2011 The Apache Software Foundation
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
'''


def get_conf_dir():
  try:
    conf_dir = os.environ[AMBARI_CONF_VAR]
    return conf_dir
  except KeyError:
    default_conf_dir = "/etc/ambari-server/conf"
    print AMBARI_CONF_VAR + " is not set, using default " + default_conf_dir
    return default_conf_dir


def find_properties_file():
  conf_file = search_file(AMBARI_PROPERTIES_FILE, get_conf_dir())
  if conf_file is None:
    err = 'File %s not found in search path $%s: %s' % (AMBARI_PROPERTIES_FILE,
          AMBARI_CONF_VAR, get_conf_dir())
    print err
    raise FatalException(1, err)
  else:
    print_info_msg ('Loading properties from ' + conf_file)
  return conf_file


def update_ambari_properties():
  prev_conf_file = search_file(AMBARI_PROPERTIES_RPMSAVE_FILE, get_conf_dir())
  conf_file = search_file(AMBARI_PROPERTIES_FILE, get_conf_dir())

  # Previous config file does not exist
  if (not prev_conf_file) or (prev_conf_file is None):
    print_warning_msg("Can not find ambari.properties.rpmsave file from previous version, skipping import of settings")
    return 0

  try:
    old_properties = Properties()
    old_properties.load(open(prev_conf_file))
  except Exception, e:
    print 'Could not read "%s": %s' % (prev_conf_file, e)
    return -1

  try:
    new_properties = Properties()
    new_properties.load(open(conf_file))

    for prop_key, prop_value in old_properties.getPropertyDict().items():
      if ("agent.fqdn.service.url" == prop_key):
        #BUG-7179 what is agent.fqdn property in ambari.props?
        new_properties.process_pair(GET_FQDN_SERVICE_URL,prop_value)
      else:
        new_properties.process_pair(prop_key,prop_value)

    # Adding custom user name property if it is absent
    # In previous versions without custom user support server was started as
    # "root" anyway so it's a reasonable default
    if not NR_USER_PROPERTY in new_properties.keys():
      new_properties.process_pair(NR_USER_PROPERTY, "root")

    new_properties.store(open(conf_file,'w'))

  except Exception, e:
    print 'Could not write "%s": %s' % (conf_file, e)
    return -1

  timestamp = datetime.datetime.now()
  format = '%Y%m%d%H%M%S'
  os.rename(prev_conf_file, prev_conf_file + '.' + timestamp.strftime(format))

  return 0


NR_CONF_DIR = get_conf_dir()

# ownership/permissions mapping
# path - permissions - user - group - recursive
# Rules are executed in the same order as they are listed
# {0} in user/group will be replaced by customized ambari-server username
NR_ADJUST_OWNERSHIP_LIST =[

  ( "/var/log/ambari-server", "644", "{0}", True ),
  ( "/var/log/ambari-server", "755", "{0}", False ),
  ( "/var/run/ambari-server", "644", "{0}", True),
  ( "/var/run/ambari-server", "755", "{0}", False),
  ( "/var/run/ambari-server/bootstrap", "755", "{0}", False ),
  ( "/var/lib/ambari-server/ambari-env.sh", "700", "{0}", False ),
  ( "/var/lib/ambari-server/keys", "600", "{0}", True ),
  ( "/var/lib/ambari-server/keys", "700", "{0}", False ),
  ( "/var/lib/ambari-server/keys/db", "700", "{0}", False ),
  ( "/var/lib/ambari-server/keys/db/newcerts", "700", "{0}", False ),
  ( "/var/lib/ambari-server/keys/.ssh", "700", "{0}", False ),
  ( "/etc/ambari-server/conf", "644", "{0}", True ),
  ( "/etc/ambari-server/conf", "755", "{0}", False ),
  ( "/etc/ambari-server/conf/password.dat", "640", "{0}", False ),
  # Also, /etc/ambari-server/conf/password.dat
  # is generated later at store_password_file
]



### System interaction ###

class FatalException(Exception):
    def __init__(self, code, reason):
      self.code = code
      self.reason = reason

    def __str__(self):
        return repr("Fatal exception: %s, exit code %s" % (self.reason, self.code))

    def _get_message(self):
      return str(self)

class NonFatalException(Exception):
  def __init__(self, reason):
    self.reason = reason

  def __str__(self):
    return repr("NonFatal exception: %s" % self.reason)

  def _get_message(self):
    return str(self)

def is_root():
  '''
  Checks effective UUID
  Returns True if a program is running under root-level privileges.
  '''
  return os.geteuid() == 0


def get_exec_path(cmd):
  cmd = 'which {0}'.format(cmd)
  ret, out, err = run_in_shell(cmd)
  if ret == 0:
    return out.strip()
  else:
    return None


def run_in_shell(cmd):
  print_info_msg('about to run command: ' + str(cmd))
  process = subprocess.Popen(cmd,
                             stdout=subprocess.PIPE,
                             stdin=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             shell=True
  )
  (stdoutdata, stderrdata) = process.communicate()
  return process.returncode, stdoutdata, stderrdata


def run_os_command(cmd):
  print_info_msg('about to run command: ' + str(cmd))
  if type(cmd) == str:
    cmd = shlex.split(cmd)
  process = subprocess.Popen(cmd,
                             stdout=subprocess.PIPE,
                             stdin=subprocess.PIPE,
                             stderr=subprocess.PIPE
  )
  (stdoutdata, stderrdata) = process.communicate()
  return process.returncode, stdoutdata, stderrdata

#
# Updates metainfo information from stack root. Re-cache information from
# repoinfo.xml , metainfo.xml files , etc.
#
def update_metainfo(args):
  configure_update_metainfo_args(args)

  hostname = args.hostname
  port = args.port
  username = args.username
  password = args.password

  command = UPDATE_METAINFO_CMD
  command = command.format(hostname, port, username, password)
  retcode, outdata, errdata = run_os_command(command)

  if outdata.find("Bad credentials") > 0:
    print 'Incorrect credential provided. Please try again.'

  if not retcode == 0:
    print errdata
  return retcode

def configure_update_metainfo_args(args):
  conf_file = search_file(AMBARI_PROPERTIES_FILE, get_conf_dir())
  properties = Properties()

  try:
    properties.load(open(conf_file))
  except Exception, e:
    print 'Could not read ambari config file "%s": %s' % (conf_file, e)
    return -1


  default_username = "admin"

  username_prompt = 'Username [' + default_username + ']: '
  password_prompt = 'Password: '
  input_pattern = "^[a-zA-Z_][a-zA-Z0-9_\-]*$"

  hostname = socket.gethostname()
  port = properties[CLIENT_API_PORT_PROPERTY]

  if not port:
    port = CLIENT_API_PORT

  input_descr = "Invalid characters in received. Start with _ or alpha "\
                  "followed by alphanumeric or _ or - characters"

  print 'Full authentication is required to access the Ambari API'
  username = get_validated_string_input(username_prompt, default_username,
      input_pattern, input_descr, False)
  password = get_validated_string_input(password_prompt, "", input_pattern,
      input_descr, True)

  args.hostname = hostname
  args.port = port
  args.username = username
  args.password = password

#
# Checks SELinux
#
def check_selinux():
  try:
    retcode, out, err = run_os_command(GET_SE_LINUX_ST_CMD)
    se_status = re.search('(disabled|enabled)', out).group(0)
    print "SELinux status is '" + se_status + "'"
    if se_status == SE_STATUS_DISABLED:
      return 0
    else:
      try:
        se_mode = re.search('(enforcing|permissive)', out).group(0)
      except AttributeError:
        err = "Error determining SELinux mode. Exiting."
        raise FatalException(1, err)
      print "SELinux mode is '" + se_mode + "'"
      if se_mode == SE_MODE_ENFORCING:
        print "Temporarily disabling SELinux"
        run_os_command(SE_SETENFORCE_CMD)
      print_warning_msg(
        "SELinux is set to 'permissive' mode and temporarily disabled.")
      ok = get_YN_input("OK to continue [y/n] (y)? ", True)
      if not ok:
        raise FatalException(1, None)
      return 0
  except OSError:
    print_warning_msg("Could not run {0}: OK".format(GET_SE_LINUX_ST_CMD))
  return 0


def read_ambari_user():
  '''
  Reads ambari user from properties file
  '''
  conf_file = find_properties_file()
  try:
    properties = Properties()
    properties.load(open(conf_file))
    user = properties[NR_USER_PROPERTY]
    if user:
      return user
    else:
      return None
  except Exception, e:
    print_error_msg('Could not read "%s": %s' % (conf_file, e))
    return None


def adjust_directory_permissions(ambari_user):
  properties = get_ambari_properties()
  bootstrap_dir = get_value_from_properties(properties, BOOTSTRAP_DIR_PROPERTY)
  print_info_msg("Cleaning bootstrap directory ({0}) contents...".format(bootstrap_dir))
  cmd = RECURSIVE_RM_CMD.format(bootstrap_dir)
  run_os_command(cmd)
  os.mkdir(bootstrap_dir)
  # Add master key and credential store if exists
  keyLocation = get_master_key_location(properties)
  masterKeyFile = search_file(SECURITY_MASTER_KEY_FILENAME, keyLocation)
  if masterKeyFile:
    NR_ADJUST_OWNERSHIP_LIST.append((masterKeyFile, "600", "{0}", "{0}", False))
  credStoreFile = get_credential_store_location(properties)
  if os.path.exists(credStoreFile):
    NR_ADJUST_OWNERSHIP_LIST.append((credStoreFile, "600", "{0}", "{0}", False))
  trust_store_location = properties[SSL_TRUSTSTORE_PATH_PROPERTY]
  if trust_store_location:
    NR_ADJUST_OWNERSHIP_LIST.append((trust_store_location, "600", "{0}", "{0}", False))
  print "Adjusting ambari-server permissions and ownership..."
  for pack in NR_ADJUST_OWNERSHIP_LIST:
    file = pack[0]
    mod = pack[1]
    user = pack[2].format(ambari_user)
    recursive = pack[3]
    set_file_permissions(file, mod, user, recursive)


def set_file_permissions(file, mod, user, recursive):
  WARN_MSG = "Command {0} returned exit code {1} with message: {2}"
  if recursive:
    params = " -R "
  else:
    params = ""
  if os.path.exists(file):
    command = NR_CHMOD_CMD.format(params, mod, file)
    retcode, out, err = run_os_command(command)
    if retcode != 0 :
      print_warning_msg(WARN_MSG.format(command, file, err))
    command = NR_CHOWN_CMD.format(params, user, file)
    retcode, out, err = run_os_command(command)
    if retcode != 0 :
      print_warning_msg(WARN_MSG.format(command, file, err))
  else:
    print_info_msg("File %s does not exist" % file)


def create_custom_user():
  user = get_validated_string_input(
    "Enter user account for ambari-server daemon (root):",
    "root",
    "^[a-z_][a-z0-9_-]{1,31}$",
    "Invalid username.",
    False
  )

  print_info_msg("Trying to create user {0}".format(user))
  command = NR_USERADD_CMD.format(user, NR_USER_COMMENT)
  retcode, out, err = run_os_command(command)
  if retcode == 9: # 9 = username already in use
    print_info_msg("User {0} already exists, "
                      "skipping user creation".format(user))

  elif retcode != 0: # fail
    print_warning_msg("Can't create user {0}. Command {1} "
                      "finished with {2}: \n{3}".format(user, command, retcode, err))
    return retcode, None

  print_info_msg("User configuration is done.")
  return 0, user


def check_ambari_user():
  try:
    user = read_ambari_user()
    create_user = False
    update_user_setting = False
    if user is not None:
      create_user = get_YN_input("Ambari-server daemon is configured to run under user '{0}'."
                        " Change this setting [y/n] (n)? ".format(user), False)
      update_user_setting = create_user # Only if we will create another user
    else: # user is not configured yet
      update_user_setting = True # Write configuration anyway
      create_user = get_YN_input("Customize user account for ambari-server "
                   "daemon [y/n] (n)? ", False)
      if not create_user:
        user = "root"

    if create_user:
      (retcode, user) = create_custom_user()
      if retcode != 0:
        return retcode

    if update_user_setting:
      write_property(NR_USER_PROPERTY, user)

    adjust_directory_permissions(user)
  except OSError:
    print_error_msg("Failed: %s" % OSError.message)
    return 4
  except Exception as e:
    print_error_msg("Unexpected error %s" % e.message)
    return 1
  return 0



#
# Checks iptables
#
def check_iptables():
  # not used
  # retcode, out, err = run_os_command(IP_TBLS_ST_CMD)
  ''' This check doesn't work on CentOS 6.2 if firewall AND
  iptables service are running if out == IP_TBLS_ENABLED:
    print 'iptables is enabled now'
    print 'Stopping iptables service'
  '''
  retcode, out, err = run_os_command(IP_TBLS_STOP_CMD)
  print 'iptables is disabled now. please reenable later.'

  if not retcode == 0 and err and len(err) > 0:
    print err

  if err.strip() == IP_TBLS_SRVC_NT_FND:
    return 0
  else:
    return retcode, out



### Postgres ###


def configure_pg_hba_ambaridb_users():
  args = optparse.Values()
  configure_database_username_password(args)

  with open(PG_HBA_CONF_FILE, "a") as pgHbaConf:
    pgHbaConf.write("\n")
    pgHbaConf.write("local  all  " + args.database_username +
                    ",mapred md5")
    pgHbaConf.write("\n")
    pgHbaConf.write("host  all   " + args.database_username +
                    ",mapred 0.0.0.0/0  md5")
    pgHbaConf.write("\n")
    pgHbaConf.write("host  all   " + args.database_username +
                    ",mapred ::/0 md5")
    pgHbaConf.write("\n")
  command = PG_HBA_RELOAD_CMD.format(PG_HBA_DIR)
  retcode, out, err = run_os_command(command)
  if not retcode == 0:
    raise FatalException(retcode, err)



def configure_pg_hba_postgres_user():
  postgresString = "all   postgres"
  for line in fileinput.input(PG_HBA_CONF_FILE, inplace=1):
    print re.sub('all\s*all', postgresString, line),
  os.chmod(PG_HBA_CONF_FILE, 0644)



def configure_postgresql_conf():
  listenAddress = "listen_addresses = '*'        #"
  for line in fileinput.input(POSTGRESQL_CONF_FILE, inplace=1):
    print re.sub('#+listen_addresses.*?(#|$)', listenAddress, line),
  os.chmod(POSTGRESQL_CONF_FILE, 0644)



def configure_postgres():
  if os.path.isfile(PG_HBA_CONF_FILE):
    if not os.path.isfile(PG_HBA_CONF_FILE_BACKUP):
      shutil.copyfile(PG_HBA_CONF_FILE, PG_HBA_CONF_FILE_BACKUP)
    else:
      #Postgres has been configured before, must not override backup
      print "Backup for pg_hba found, reconfiguration not required"
      return 0
  configure_pg_hba_postgres_user()
  configure_pg_hba_ambaridb_users()
  os.chmod(PG_HBA_CONF_FILE, 0644)
  configure_postgresql_conf()
  #restart postgresql if already running
  pg_status = get_postgre_status()
  if pg_status == PG_STATUS_RUNNING:
    retcode = restart_postgres()
    return retcode
  return 0



def restart_postgres():
  print "Restarting PostgreSQL"
  process = subprocess.Popen(PG_RESTART_CMD.split(' '),
    stdout=subprocess.PIPE,
    stdin=subprocess.PIPE,
    stderr=subprocess.PIPE
  )
  time.sleep(5)
  result = process.poll()
  if result is None:
    print_info_msg("Killing restart PostgresSQL process")
    process.kill()
    pg_status = get_postgre_status()
    # SUSE linux set status of stopped postgresql proc to unused
    if pg_status == "unused" or pg_status == "stopped":
      print_info_msg("PostgreSQL is stopped. Restarting ...")
      retcode, out, err = run_os_command(PG_START_CMD)
      return retcode
  return 0


# todo: check if the scheme is already exist

def write_property(key, value):
  conf_file = find_properties_file()
  properties = Properties()
  try:
    properties.load(open(conf_file))
  except Exception, e:
    print_error_msg('Could not read ambari config file "%s": %s' % (conf_file, e))
    return -1
  properties.process_pair(key, value)
  try:
    properties.store(open(conf_file, "w"))
  except Exception, e:
    print_error_msg('Could not write ambari config file "%s": %s' % (conf_file, e))
    return -1
  return 0


def setup_db(args):
  #password access to ambari-server and mapred
  configure_database_username_password(args)
  dbname = args.database_name
  scriptFile = args.init_script_file
  username = args.database_username
  password = args.database_password

  #setup DB
  command = SETUP_DB_CMD[:]
  command[-1] = command[-1].format(scriptFile, username, password, dbname)

  retcode, outdata, errdata = run_os_command(command)
  if not retcode == 0:
    print errdata
  return retcode


def store_password_file(password, filename):
  conf_file = find_properties_file()
  passFilePath = os.path.join(os.path.dirname(conf_file),
    filename)

  with open(passFilePath, 'w+') as passFile:
    passFile.write(password)
  print_info_msg("Adjusting filesystem permissions")  
  ambari_user = read_ambari_user()
  set_file_permissions(passFilePath, "660", ambari_user, False)

  return passFilePath

def remove_password_file(filename):
  conf_file = find_properties_file()
  passFilePath = os.path.join(os.path.dirname(conf_file),
    filename)

  if os.path.exists(passFilePath):
    try:
      os.remove(passFilePath)
    except Exception, e:
      print_warning_msg('Unable to remove password file: ' + str(e))
      return 1
  pass
  return 0

def execute_db_script(args, file):
  #password access to ambari-server and mapred
  configure_database_username_password(args)
  dbname = args.database_name
  username = args.database_username
  password = args.database_password
  command = SETUP_DB_CMD[:]
  command[-1] = command[-1].format(file, username, password, dbname)
  retcode, outdata, errdata = run_os_command(command)
  if not retcode == 0:
    print errdata
  return retcode


def check_db_consistency(args, file):
  #password access to ambari-server and mapred
  configure_database_username_password(args)
  dbname = args.database_name
  username = args.database_username
  password = args.database_password
  command = SETUP_DB_CMD[:]
  command[-1] = command[-1].format(file, username, password, dbname)
  retcode, outdata, errdata = run_os_command(command)
  if not retcode == 0:
    print errdata
    return retcode
  else:
    # Assumes that the output is of the form ...\n<count>
    print_info_msg("Parsing output: " + outdata)
    lines = outdata.splitlines()
    if (lines[-1] == '3' or lines[-1] == '0'):
      return 0
  return -1



def get_postgre_status():
  retcode, out, err = run_os_command(PG_ST_CMD)
  try:
    pg_status = re.search('(stopped|running)', out).group(0)
  except AttributeError:
    pg_status = None
  return pg_status



def check_postgre_up():
  pg_status = get_postgre_status()
  if pg_status == PG_STATUS_RUNNING:
    print_info_msg ("PostgreSQL is running")
    return 0
  else:
    print "Running initdb: This may take upto a minute."
    retcode, out, err = run_os_command(PG_INITDB_CMD)
    if retcode == 0:
      print out
    print "About to start PostgreSQL"
    try:
      process = subprocess.Popen(PG_START_CMD.split(' '),
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE
      )
      time.sleep(20)
      result = process.poll()
      print_info_msg("Result of postgres start cmd: " + str(result))
      if result is None:
        process.kill()
        pg_status = get_postgre_status()
        if pg_status == PG_STATUS_RUNNING:
          print_info_msg("Postgres process is running. Returning...")
          return 0
      else:
        retcode = result
    except (Exception), e:
      pg_status = get_postgre_status()
      if pg_status == PG_STATUS_RUNNING:
        return 0
      else:
        print_error_msg("Postgres start failed. " + str(e))
        return 1
    return retcode


def get_validated_db_name(database_name):
  return get_validated_string_input(
        DATABASE_STORAGE_NAMES[DATABASE_INDEX] + " Name (" 
        + database_name + "): ",
        database_name,
        ".*",
        "Invalid " + DATABASE_STORAGE_NAMES[DATABASE_INDEX] + " name.",
        False
        )
  
def get_validated_service_name(service_name, index):
  return get_validated_string_input(
            ORACLE_DB_ID_TYPES[index] + " (" + service_name + "): ",
            service_name,
            ".*",
            "Invalid " + ORACLE_DB_ID_TYPES[index] + ".",
            False
            )

def read_password(passwordDefault=PG_DEFAULT_PASSWORD,
                  passwordPattern=PASSWORD_PATTERN,
                  passwordPrompt=None,
                  passwordDescr=None):
  # setup password
  if passwordPrompt is None:
    passwordPrompt = 'Password (' + passwordDefault + '): '

  if passwordDescr is None:
    passwordDescr = "Invalid characters in password. Use only alphanumeric or " \
                    "_ or - characters"

  password = get_validated_string_input(passwordPrompt, passwordDefault,
                                        passwordPattern, passwordDescr, True)

  if not password:
    print 'Password cannot be blank.'
    return read_password(passwordDefault, passwordPattern, passwordPrompt,
                   passwordDescr)

  if password != passwordDefault:
    password1 = get_validated_string_input("Re-enter password: ",
                                           passwordDefault, passwordPattern, passwordDescr, True)
    if password != password1:
      print "Passwords do not match"
      return read_password(passwordDefault, passwordPattern, passwordPrompt,
                      passwordDescr)

  return password



def get_pass_file_path(conf_file):
  return os.path.join(os.path.dirname(conf_file),
                      JDBC_PASSWORD_FILENAME)


# Set database properties to default values
def load_default_db_properties(args):
  args.database=DATABASE_NAMES[DATABASE_INDEX]
  args.database_host = "localhost"
  args.database_port = DATABASE_PORTS[DATABASE_INDEX]
  args.database_name = "ambari"
  args.database_username = "ambari"
  args.database_password = "bigdata"
  args.sid_or_sname = "sname"
  pass


# Ask user for database conenction properties
def prompt_db_properties(args):
  global DATABASE_INDEX

  if PROMPT_DATABASE_OPTIONS:
    load_default_db_properties(args)
    ok = get_YN_input("Enter advanced database configuration [y/n] (n)? ", False)
    if ok:

      database_num = str(DATABASE_INDEX + 1)
      database_num = get_validated_string_input(
        "Select database:\n1 - PostgreSQL (Embedded)\n2 - Oracle\n(" + database_num + "): ",
        database_num,
        "^[12]$",
        "Invalid number.",
        False
      )

      DATABASE_INDEX = int(database_num) - 1
      args.database = DATABASE_NAMES[DATABASE_INDEX]
      
      if args.database != "postgres" :
        args.database_host = get_validated_string_input(
          "Hostname (" + args.database_host + "): ",
          args.database_host,
          "^[a-zA-Z0-9.\-]*$",
          "Invalid hostname.",
          False
        )
  
        args.database_port=DATABASE_PORTS[DATABASE_INDEX]
        args.database_port = get_validated_string_input(
          "Port (" + args.database_port + "): ",
          args.database_port,
          "^([0-9]{1,4}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$",
          "Invalid port.",
          False
        )

        if args.database == "oracle":
          # Oracle uses service name or service id
          idType = "1"
          idType = get_validated_string_input(
            "Select Oracle identifier type:\n1 - " + ORACLE_DB_ID_TYPES[0] +
            "\n2 - " + ORACLE_DB_ID_TYPES[1] + "\n(" + idType + "): ",
            idType,
            "^[12]$",
            "Invalid number.",
            False
          )

          if idType == "2":
            args.sid_or_sname = "sid"

          IDTYPE_INDEX = int(idType) - 1
          args.database_name = get_validated_service_name(args.database_name, 
                                                          IDTYPE_INDEX)
        else:
          # MySQL and other DB types
          pass
        pass
      else:
        args.database_host = "localhost"
        args.database_port = DATABASE_PORTS[DATABASE_INDEX]

        args.database_name = get_validated_db_name(args.database_name)
        pass
      
      # Username is common for Oracle/MySQL/Postgres
      args.database_username = get_validated_string_input(
        'Username (' + args.database_username + '): ',
        args.database_username,
        USERNAME_PATTERN,
        "Invalid characters in username. Start with _ or alpha "
        "followed by alphanumeric or _ or - characters",
        False
      )
      args.database_password =  configure_database_password(True)

  print_info_msg('Using database options: {database},{host},{port},{schema},{user},{password}'.format(
    database=args.database,
    host=args.database_host,
    port=args.database_port,
    schema=args.database_name,
    user=args.database_username,
    password=args.database_password
  ))


# Store set of properties for remote database connection
def store_remote_properties(args):
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return -1

  isSecure = get_is_secure(properties)

  properties.process_pair(PERSISTENCE_TYPE_PROPERTY, "remote")

  properties.process_pair(JDBC_DATABASE_PROPERTY, args.database)
  properties.process_pair(JDBC_HOSTNAME_PROPERTY, args.database_host)
  properties.process_pair(JDBC_PORT_PROPERTY, args.database_port)
  properties.process_pair(JDBC_SCHEMA_PROPERTY, args.database_name)

  properties.process_pair(JDBC_DRIVER_PROPERTY, DATABASE_DRIVER_NAMES[DATABASE_INDEX])
  # fully qualify the hostname to make sure all the other hosts can connect
  # to the jdbc hostname since its passed onto the agents for RCA
  jdbc_hostname = args.database_host
  if (args.database_host == "localhost"):
    jdbc_hostname = socket.getfqdn();
    
  connectionStringFormat = DATABASE_CONNECTION_STRINGS
  if args.sid_or_sname == "sid":
    connectionStringFormat = DATABASE_CONNECTION_STRINGS_ALT
  properties.process_pair(JDBC_URL_PROPERTY, connectionStringFormat[DATABASE_INDEX].format(jdbc_hostname, args.database_port, args.database_name))
  properties.process_pair(JDBC_USER_NAME_PROPERTY, args.database_username)
  properties.process_pair(JDBC_PASSWORD_PROPERTY,
      store_password_file(args.database_password, JDBC_PASSWORD_FILENAME))
  
  # save any other defined properties to pass to JDBC
  if DATABASE_INDEX < len(DATABASE_JDBC_PROPERTIES):
    for pair in DATABASE_JDBC_PROPERTIES[DATABASE_INDEX]:
      properties.process_pair(JDBC_PROPERTIES_PREFIX + pair[0], pair[1])

  if isSecure:
    encrypted_password = encrypt_password(JDBC_RCA_PASSWORD_ALIAS, args.database_password)
    if encrypted_password != args.database_password:
      properties.process_pair(JDBC_PASSWORD_PROPERTY, encrypted_password)
  pass

  properties.process_pair(JDBC_RCA_DRIVER_PROPERTY, DATABASE_DRIVER_NAMES[DATABASE_INDEX])
  properties.process_pair(JDBC_RCA_URL_PROPERTY, connectionStringFormat[DATABASE_INDEX].format(jdbc_hostname, args.database_port, args.database_name))
  properties.process_pair(JDBC_RCA_USER_NAME_PROPERTY, args.database_username)
  properties.process_pair(JDBC_RCA_PASSWORD_FILE_PROPERTY,
      store_password_file(args.database_password, JDBC_PASSWORD_FILENAME))
  if isSecure:
    encrypted_password = encrypt_password(JDBC_RCA_PASSWORD_ALIAS, args.database_password)
    if encrypted_password != args.database_password:
      properties.process_pair(JDBC_RCA_PASSWORD_FILE_PROPERTY, encrypted_password)
  pass

  conf_file = properties.fileName

  try:
    properties.store(open(conf_file, "w"))
  except Exception, e:
    print 'Could not write ambari config file "%s": %s' % (conf_file, e)
    return -1

  return 0


# Initialize remote database schema
def setup_remote_db(args):

  not_found_msg = "Cannot find {0} {1} client in the path to load the Ambari Server schema.\
 Before starting Ambari Server, you must run the following DDL against the database to create \
the schema ".format(DATABASE_NAMES[DATABASE_INDEX], str(DATABASE_CLI_TOOLS_DESC[DATABASE_INDEX]))
  client_usage_cmd = DATABASE_CLI_TOOLS_USAGE[DATABASE_INDEX].format(DATABASE_INIT_SCRIPTS[DATABASE_INDEX], args.database_username,
                                                     BLIND_PASSWORD, args.database_name)

  retcode, out, err = execute_remote_script(args, DATABASE_INIT_SCRIPTS[DATABASE_INDEX])
  if retcode != 0:
    if retcode == -1:
      print_warning_msg(not_found_msg + os.linesep + client_usage_cmd)
      if not SILENT:
        raw_input(PRESS_ENTER_MSG)
      return retcode

    print err
    print_error_msg('Database bootstrap failed. Please, provide correct connection properties.')
    return retcode

  return 0

# Get database client executable path
def get_db_cli_tool(args):
  for tool in DATABASE_CLI_TOOLS[DATABASE_INDEX]:
    cmd =CHECK_COMMAND_EXIST_CMD.format(tool)
    ret, out, err = run_in_shell(cmd)
    if ret == 0:
      return get_exec_path(tool)

  return None


#execute SQL script on remote database
def execute_remote_script(args, scriptPath):
  tool = get_db_cli_tool(args)
  if not tool:
    args.warnings.append('{0} not found. Please, run DDL script manually'.format(DATABASE_CLI_TOOLS[DATABASE_INDEX]))
    if VERBOSE:
      print_warning_msg('{0} not found'.format(DATABASE_CLI_TOOLS[DATABASE_INDEX]))
    return -1, "Client wasn't found", "Client wasn't found"

  if args.database == "postgres":

    os.environ["PGPASSWORD"] = args.database_password
    retcode, out, err = run_in_shell('{0} {1}'.format(tool,  POSTGRES_EXEC_ARGS.format(
      args.database_host,
      args.database_port,
      args.database_name,
      args.database_username,
      scriptPath
    )))
    return retcode, out, err
  elif args.database == "oracle":
    retcode, out, err = run_in_shell('{0} {1}'.format(tool, ORACLE_EXEC_ARGS.format(
      args.database_username,
      args.database_password,
      args.database_host,
      args.database_port,
      args.database_name,
      scriptPath
    )))
    return retcode, out, err
  elif args.database=="mysql":
    retcode, out, err = run_in_shell('{0} {1}'.format(tool, MYSQL_EXEC_ARGS.format(
      args.database_host,
      args.database_port,
      args.database_username,
      args.database_password,
      args.database_name,
      scriptPath
    )))
    return retcode, out, err

  return -2, "Wrong database", "Wrong database"


def configure_database_password(showDefault=True):
  passwordDefault = PG_DEFAULT_PASSWORD
  if showDefault:
    passwordPrompt = 'Enter Database Password (' + passwordDefault + '): '
  else:
    passwordPrompt = 'Enter Database Password: '
  passwordPattern = "^[a-zA-Z0-9_-]*$"
  passwordDescr = "Invalid characters in password. Use only alphanumeric or "\
                  "_ or - characters"

  password = read_password(passwordDefault, passwordPattern, passwordPrompt,
    passwordDescr)

  return password


def configure_database_username_password(args):
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return -1

  username = properties[JDBC_USER_NAME_PROPERTY]
  passwordProp = properties[JDBC_PASSWORD_PROPERTY]

  if username and passwordProp:
    print_info_msg("Database username + password already configured")
    args.database_username=username
    if is_alias_string(passwordProp):
      args.database_password = decrypt_password_for_alias(JDBC_RCA_PASSWORD_ALIAS)
    else:
      if os.path.exists(passwordProp):
        with open(passwordProp, 'r') as file:
          args.database_password = file.read()

    return 1
  else:
    print_error_msg("Connection properties not set in config file.")

# Check if jdbc user is changed
def is_jdbc_user_changed(args):
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return None

  previos_user = properties[JDBC_USER_NAME_PROPERTY]
  new_user = args.database_username

  if previos_user and new_user:
    if previos_user != new_user:
      return True
  else:
    print_error_msg("Connection properties not set in config file.")
    return None

  return False

# Store local database connection properties
def store_local_properties(args):
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return -1

  isSecure = get_is_secure(properties)

  properties.removeOldProp(JDBC_SCHEMA_PROPERTY)
  properties.removeOldProp(JDBC_HOSTNAME_PROPERTY)
  properties.removeOldProp(JDBC_RCA_DRIVER_PROPERTY)
  properties.removeOldProp(JDBC_RCA_URL_PROPERTY)
  properties.removeOldProp(JDBC_PORT_PROPERTY)
  properties.removeOldProp(JDBC_DRIVER_PROPERTY)
  properties.removeOldProp(JDBC_URL_PROPERTY)
  #properties.removeOldProp(JDBC_DATABASE_PROPERTY)
  properties.process_pair(PERSISTENCE_TYPE_PROPERTY, "local")
  properties.process_pair(JDBC_DATABASE_PROPERTY, args.database_name)
  properties.process_pair(JDBC_USER_NAME_PROPERTY, args.database_username)
  properties.process_pair(JDBC_PASSWORD_PROPERTY,
      store_password_file(args.database_password, JDBC_PASSWORD_FILENAME))

  if isSecure:
    encrypted_password = encrypt_password(JDBC_RCA_PASSWORD_ALIAS, args.database_password)
    if args.database_password != encrypted_password:
      properties.process_pair(JDBC_PASSWORD_PROPERTY, encrypted_password)
    pass
  pass

  conf_file = properties.fileName

  try:
    properties.store(open(conf_file, "w"))
  except Exception, e:
    print 'Unable to write ambari.properties configuration file "%s": %s' % (conf_file, e)
    return -1
  return 0


# Load ambari properties and return dict with values
def get_ambari_properties():
  conf_file = find_properties_file()

  properties = None
  try:
    properties = Properties()
    properties.load(open(conf_file))
  except (Exception), e:
    print 'Could not read "%s": %s' % (conf_file, e)
    return -1
  return properties


# Load database connection properties from conf file
def parse_properties_file(args):
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return -1

  args.persistence_type = properties[PERSISTENCE_TYPE_PROPERTY]

  if not args.persistence_type:
    args.persistence_type = "local"

  if args.persistence_type == 'remote':
    args.database = properties[JDBC_DATABASE_PROPERTY]
    args.database_host = properties[JDBC_HOSTNAME_PROPERTY]
    args.database_port = properties[JDBC_PORT_PROPERTY]
    args.database_name = properties[JDBC_SCHEMA_PROPERTY]
    global DATABASE_INDEX
    try:
      DATABASE_INDEX = DATABASE_NAMES.index(args.database)
    except ValueError:
      pass

  args.database_username = properties[JDBC_USER_NAME_PROPERTY]
  args.database_name = properties[JDBC_DATABASE_PROPERTY]
  args.database_password_file = properties[JDBC_PASSWORD_PROPERTY]
  if args.database_password_file:
    if not is_alias_string(args.database_password_file):
      args.database_password = open(properties[JDBC_PASSWORD_PROPERTY]).read()
    else:
      args.database_password = args.database_password_file

  return 0


### JDK ###


def get_ambari_jars():
  try:
    conf_dir = os.environ[AMBARI_SERVER_LIB]
    return conf_dir
  except KeyError:
    default_jar_location = "/usr/lib/ambari-server"
    print_info_msg(AMBARI_SERVER_LIB + " is not set, using default "
                 + default_jar_location)
    return default_jar_location


def get_share_jars():
  share_jars = ""
  file_list = []
  file_list.extend(glob.glob(JAVA_SHARE_PATH + os.sep + "*mysql*"))
  file_list.extend(glob.glob(JAVA_SHARE_PATH + os.sep + "*ojdbc*"))
  if len(file_list) > 0:
    share_jars = string.join(file_list, os.pathsep)
  return share_jars


def get_ambari_classpath():
  ambari_cp = get_ambari_jars() + os.sep + "*"
  share_cp = get_share_jars()
  if len(share_cp) > 0:
    ambari_cp = ambari_cp + os.pathsep + share_cp
  return ambari_cp






def search_file(filename, search_path, pathsep=os.pathsep):
  """ Given a search path, find file with requested name """
  for path in string.split(search_path, pathsep):
    candidate = os.path.join(path, filename)
    if os.path.exists(candidate): return os.path.abspath(candidate)
  return None



def dlprogress(base_name, count, blockSize, totalSize):
  percent = int(count * blockSize * 100 / totalSize)

  if (totalSize < blockSize):
    sys.stdout.write("\r" + base_name + "... %d%%" % (100))
  else:
    sys.stdout.write("\r" + base_name + "... %d%% (%.1f MB of %.1f MB)" % (
      percent, count * blockSize / 1024 / 1024.0, totalSize / 1024 / 1024.0))

  if (percent == 100 or totalSize < blockSize):
    sys.stdout.write("\n")
  sys.stdout.flush()



def track_jdk(base_name, url, local_name):
  u = urllib2.urlopen(url)
  h = u.info()
  totalSize = int(h["Content-Length"])
  fp = open(local_name, "wb")
  blockSize = 8192
  count = 0
  percent = 0
  while True:
    chunk = u.read(blockSize)
    if not chunk:
      break
    fp.write(chunk)
    count += 1

    dlprogress(base_name, count, blockSize, totalSize)

  fp.flush()
  fp.close()

def install_jce_manualy(args):
  properties = get_ambari_properties()
  if properties == -1:
    err = "Error getting ambari properties"
    raise FatalException(-1, err)
  if args.jce_policy and os.path.exists(args.jce_policy):
    jce_destination = os.path.join(properties[RESOURCES_DIR_PROPERTY], JCE_POLICY_FILENAME)
    shutil.copy(args.jce_policy, jce_destination)
    print "JCE policy copied from " + args.jce_policy + " to " + jce_destination
    return 0
  else:
    return 1
#
# Downloads the JDK
#
def download_jdk(args):
  jce_installed = install_jce_manualy(args)
  properties = get_ambari_properties()
  if properties == -1:
    err = "Error getting ambari properties"
    raise FatalException(-1, err)
  conf_file = properties.fileName
  ok = False
  if get_JAVA_HOME() and not args.java_home:
    pass # do nothing
  elif args.java_home and os.path.exists(args.java_home):
    print_warning_msg("JAVA_HOME " + args.java_home
                    + " must be valid on ALL hosts")
    write_property(JAVA_HOME_PROPERTY, args.java_home)
  else:
    try:
      jdk_url = properties[JDK_URL_PROPERTY]
      resources_dir = properties[RESOURCES_DIR_PROPERTY]
    except (KeyError), e:
      err = 'Property ' + str(e) + ' is not defined at ' + conf_file
      raise FatalException(1, err)
    dest_file = resources_dir + os.sep + JDK_LOCAL_FILENAME
    if os.path.exists(dest_file):
      print "JDK already exists, using " + dest_file
    elif args.jdk_location and os.path.exists(args.jdk_location):
      print "Copying local JDK file {0} to {1}".format(args.jdk_location, dest_file)
      try:
        shutil.copyfile(args.jdk_location, dest_file)
      except Exception, e:
        err = "Can not copy file {0} to {1} due to: {2} . Please check file " \
              "permissions and free disk space.".format(args.jdk_location,
                                                        dest_file, e.message)
        raise FatalException(1, err)
    else:
      print 'Downloading JDK from ' + jdk_url + ' to ' + dest_file
      jdk_download_fail_msg = " Failed to download JDK: {0}. Please check that Oracle " \
        "JDK is available at {1}. Also you may specify JDK file " \
        "location in local filesystem using --jdk-location command " \
        "line argument.".format("{0}", jdk_url)
      try:
        size_command = JDK_DOWNLOAD_SIZE_CMD.format(jdk_url);
        #Get Header from url,to get file size then
        retcode, out, err = run_os_command(size_command)
        if out.find("Content-Length") == -1:
          err = jdk_download_fail_msg.format("Request header doesn't contain Content-Length")
          raise FatalException(1, err)
        start_with = int(out.find("Content-Length") + len("Content-Length") + 2)
        end_with = out.find("\r\n", start_with)
        src_size = int(out[start_with:end_with])
        print 'JDK distribution size is ' + str(src_size) + ' bytes'
        file_exists = os.path.isfile(dest_file)
        file_size = -1
        if file_exists:
          file_size = os.stat(dest_file).st_size
        if file_exists and file_size == src_size:
          print_info_msg("File already exists")
        else:
          track_jdk(JDK_LOCAL_FILENAME, jdk_url, dest_file)
          print 'Successfully downloaded JDK distribution to ' + dest_file
      except FatalException:
        raise
      except Exception, e:
        err = jdk_download_fail_msg.format(str(e))
        raise FatalException(1, err)
      downloaded_size = os.stat(dest_file).st_size
      if downloaded_size != src_size or downloaded_size < JDK_MIN_FILESIZE:
        err = 'Size of downloaded JDK distribution file is ' \
                      + str(downloaded_size) + ' bytes, it is probably \
                      damaged or incomplete'
        raise FatalException(1, err)

    try:
       out, ok = install_jdk(dest_file)
       jdk_version = re.search('Creating (jdk.*)/jre', out).group(1)
    except Exception, e:
       print "Installation of JDK has failed: %s\n" % e.message
       file_exists = os.path.isfile(dest_file)
       if file_exists:
          ok = get_YN_input("JDK found at "+dest_file+". "
                      "Would you like to re-download the JDK [y/n] (y)? ", True)
          if not ok:
             err = "Unable to install JDK. Please remove JDK file found at "+ \
                   dest_file +" and re-run Ambari Server setup"
             raise FatalException(1, err)
          else:
             track_jdk(JDK_LOCAL_FILENAME, jdk_url, dest_file)
             print 'Successfully re-downloaded JDK distribution to ' + dest_file
             try:
                 out, ok = install_jdk(dest_file)
                 jdk_version = re.search('Creating (jdk.*)/jre', out).group(1)
             except Exception, e:
               print "Installation of JDK was failed: %s\n" % e.message
               err = "Unable to install JDK. Please remove JDK, file found at "+ \
                     dest_file +" and re-run Ambari Server setup"
               raise FatalException(1, err)

       else:
           err = "Unable to install JDK. File "+ dest_file +" does not exist, " \
                                        "please re-run Ambari Server setup"
           raise FatalException(1, err)

    print "Successfully installed JDK to {0}/{1}".\
        format(JDK_INSTALL_DIR, jdk_version)
    write_property(JAVA_HOME_PROPERTY, "{0}/{1}".
        format(JDK_INSTALL_DIR, jdk_version))

  if jce_installed != 0:
    try:
      download_jce_policy(properties, ok)
    except FatalException as e:
      print "JCE Policy files are required for secure HDP setup. Please ensure " \
              " all hosts have the JCE unlimited strength policy 6, files."
      print_error_msg("Failed to download JCE policy files:")
      if e.reason is not None:
        print_error_msg("Reason: {0}".format(e.reason))
      # TODO: We don't fail installation if download_jce_policy fails. Is it OK?
  return 0


def download_jce_policy(properties, accpeted_bcl):
  try:
    jce_url = properties[JCE_URL_PROPERTY]
    resources_dir = properties[RESOURCES_DIR_PROPERTY]
  except KeyError, e:
    err = 'Property ' + str(e) + ' is not defined in properties file'
    raise FatalException(1, err)
  dest_file = resources_dir + os.sep + JCE_POLICY_FILENAME
  if not os.path.exists(dest_file):
    print 'Downloading JCE Policy archive from ' + jce_url + ' to ' + dest_file
    jce_download_fail_msg = " Failed to download JCE Policy archive : {0}. " \
        "Please check that JCE Policy archive is available " \
        "at {1} . Also you may install JCE Policy archive manually using " \
      "--jce-policy command line argument.".format("{0}", jce_url)
    try:
      size_command = JDK_DOWNLOAD_SIZE_CMD.format(jce_url);
      #Get Header from url,to get file size then
      retcode, out, err = run_os_command(size_command)
      if out.find("Content-Length") == -1:
        err = jce_download_fail_msg.format(
            "Request header doesn't contain Content-Length")
        raise FatalException(1, err)
      start_with = int(out.find("Content-Length") + len("Content-Length") + 2)
      end_with = out.find("\r\n", start_with)
      src_size = int(out[start_with:end_with])
      print_info_msg('JCE zip distribution size is ' + str(src_size) + ' bytes')
      file_exists = os.path.isfile(dest_file)
      file_size = -1
      if file_exists:
        file_size = os.stat(dest_file).st_size
      if file_exists and file_size == src_size:
        print_info_msg("File already exists")
      else:
        #BCL license before download
        jce_download_cmd = JCE_DOWNLOAD_CMD.format(dest_file, jce_url)
        print_info_msg("JCE download cmd: " + jce_download_cmd)
        if accpeted_bcl:
          retcode, out, err = run_os_command(jce_download_cmd)
          if retcode == 0:
            print 'Successfully downloaded JCE Policy archive to ' + dest_file
          else:
            raise FatalException(1, err)
        else:
          ok = get_YN_input("To download the JCE Policy archive you must "
                            "accept the license terms found at "
                            "http://www.oracle.com/technetwork/java/javase"
                            "/terms/license/index.html"
                            "Not accepting might result in failure when "
                            "setting up HDP security. \nDo you accept the "
                            "Oracle Binary Code License Agreement [y/n] (y)? ", True)
          if ok:
            retcode, out, err = run_os_command(jce_download_cmd)
            if retcode == 0:
              print 'Successfully downloaded JCE Policy archive to ' + dest_file
          else:
            raise FatalException(1, None)
    except FatalException:
        raise
    except Exception, e:
      err = 'Failed to download JCE Policy archive: ' + str(e)
      raise FatalException(1, err)
    downloaded_size = os.stat(dest_file).st_size
    if downloaded_size != src_size or downloaded_size < JCE_MIN_FILESIZE:
      err = 'Size of downloaded JCE Policy archive is ' \
                      + str(downloaded_size) + ' bytes, it is probably \
                    damaged or incomplete'
      raise FatalException(1, err)
  else:
    print "JCE Policy archive already exists, using " + dest_file

class RetCodeException(Exception): pass

def install_jdk(dest_file):
  ok = get_YN_input("To install the Oracle JDK you must accept the "
                    "license terms found at "
                    "http://www.oracle.com/technetwork/java/javase/"
                  "downloads/jdk-6u21-license-159167.txt. Not accepting will "
                  "cancel the Ambari Server setup.\nDo you accept the "
                  "Oracle Binary Code License Agreement [y/n] (y)? ", True)
  if not ok:
    raise FatalException(1, None)

  print "Installing JDK to {0}".format(JDK_INSTALL_DIR)
  retcode, out, err = run_os_command(CREATE_JDK_DIR_CMD)
  savedPath = os.getcwd()
  os.chdir(JDK_INSTALL_DIR)
  retcode, out, err = run_os_command(MAKE_FILE_EXECUTABLE_CMD.format(dest_file))
  retcode, out, err = run_os_command(dest_file + ' -noregister')
  os.chdir(savedPath)
  if retcode != 0:
    err = "Installation of JDK returned exit code %s" % retcode
    raise FatalException(retcode, err)
  return out, ok

#
# Configures the OS settings in ambari properties.
#
def configure_os_settings():
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return -1
  try:
    conf_os_type = properties[OS_TYPE_PROPERTY]
    if conf_os_type != '':
      print_info_msg ("os_type already setting in properties file")
      return 0
  except (KeyError), e:
    print_error_msg ("os_type is not set in properties file")

  os_system = platform.system()
  if os_system != 'Linux':
    print_error_msg ("Non-Linux systems are not supported")
    return -1

  os_info = platform.linux_distribution(
    None, None, None, ['SuSE', 'redhat' ], 0
  )
  os_name = os_info[0].lower()
  if os_name == 'suse':
    os_name = 'sles'
  os_version = os_info[1].split('.', 1)[0]
  master_os_type = os_name + os_version    
  write_property(OS_TYPE_PROPERTY, master_os_type)
  return 0



def get_JAVA_HOME():
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return None
    
  java_home = properties[JAVA_HOME_PROPERTY]
  if (not 0 == len(java_home)) and (os.path.exists(java_home)):
    return java_home

  return None

#
# Finds the available JDKs.
#
def find_jdk():
  if get_JAVA_HOME():
    return get_JAVA_HOME()
  print "Looking for available JDKs at " + JDK_INSTALL_DIR
  jdks = glob.glob(JDK_INSTALL_DIR + os.sep + "jdk*")
  jdks.sort()
  print "Found: " + str(jdks)
  count = len(jdks)
  if count == 0:
    return
  jdkPath = jdks[count - 1]
  print "Selected JDK {0}".format(jdkPath)
  return jdkPath

#
# Checks if options determine local DB configuration
#
def is_local_database(options):
  if options.database == DATABASE_NAMES[0] \
    and options.database_host == "localhost" \
    and options.database_port == DATABASE_PORTS[0]:
    return True
  return False

#Check if required jdbc drivers present
def find_jdbc_driver(args):
  if args.database in JDBC_PATTERNS.keys():
    drivers = []
    drivers.extend(glob.glob(JAVA_SHARE_PATH + os.sep + JDBC_PATTERNS[args.database]))
    if drivers:
      return drivers
    return -1
  return 0
  
def copy_file(src, dest_file):
  try:
    shutil.copyfile(src, dest_file)
  except Exception, e:
    err = "Can not copy file {0} to {1} due to: {2} . Please check file " \
              "permissions and free disk space.".format(src, dest_file, e.message)
    raise FatalException(1, err)

def remove_file(filePath):
  if os.path.exists(filePath):
    try:
      os.remove(filePath)
    except Exception, e:
      print_warning_msg('Unable to remove file: ' + str(e))
      return 1
  pass
  return 0

def copy_files(files, dest_dir):
  if os.path.isdir(dest_dir):
    for filepath in files:
      shutil.copy(filepath, dest_dir)
    return 0
  else:
    return -1

def check_jdbc_drivers(args):
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return -1
  
  result = find_jdbc_driver(args)
  
  msg = 'Before starting Ambari Server, ' \
        'you must copy the {0} JDBC driver JAR file to {1}.'.format(
        DATABASE_FULL_NAMES[args.database],
        JAVA_SHARE_PATH)

  
  if result == -1:
  
    if SILENT:
      print_error_msg(msg)
      raise FatalException(-1, msg)
    else:
      print_warning_msg(msg)
      raw_input(PRESS_ENTER_MSG)
      result = find_jdbc_driver(args)
      if result == -1:
        print_error_msg(msg)
        raise FatalException(-1, msg)
        
  # Check if selected RDBMS requires drivers to copy
  if type(result) is not int:
    print 'Copying JDBC drivers to server resources...'
    try:
      resources_dir = properties[RESOURCES_DIR_PROPERTY]
    except KeyError:
      print_error_msg("There is no value for " + RESOURCES_DIR_PROPERTY + "in " + AMBARI_PROPERTIES_FILE)
      return -1

    copy_status = copy_files(result, resources_dir)
    
    if not copy_status == 0:
      raise FatalException(-1, "Failed to copy JDBC drivers to server resources")

  return 0

def verify_setup_allowed():
  properties = get_ambari_properties()
  if properties == -1:
    print_error_msg ("Error getting ambari properties")
    return -1

  isSecure = get_is_secure(properties)
  (isPersisted, masterKeyFile) = get_is_persisted(properties)
  if isSecure and not isPersisted and SILENT:
    print "ERROR: Cannot run silent 'setup' with password encryption enabled " \
          "and Master Key not persisted."
    print "Ambari Server 'setup' exiting."
    return 1
  return 0

#
# Setup the Ambari Server.
#
def setup(args):
  retcode = verify_setup_allowed()
  if not retcode == 0:
    raise FatalException(1, None)

  if not is_root():
    err = 'Ambari-server setup should be run with '\
                     'root-level privileges'
    raise FatalException(4, err)

  print 'Checking SELinux...'
  retcode = check_selinux()
  if not retcode == 0:
    err = 'Failed to disable SELinux. Exiting.'
    raise FatalException(retcode, err)

  # Create ambari user, if needed
  retcode = check_ambari_user()
  if not retcode == 0:
    err = 'Failed to create user. Exiting.'
    raise FatalException(retcode, err)

  print 'Checking iptables...'
  retcode, out = check_iptables()
  if not retcode == 0 and out == IP_TBLS_ENABLED:
    err = 'Failed to stop iptables. Exiting.'
    raise FatalException(retcode, err)

  print 'Checking JDK...'
  try:
    download_jdk(args)
  except FatalException as e:
    err = 'Downloading or installing JDK failed: {0}. Exiting.'.format(e)
    raise FatalException(e.code, err)

  print 'Completing setup...'
  retcode = configure_os_settings()
  if not retcode == 0:
    err = 'Configure of OS settings in ambari.properties failed. Exiting.'
    raise FatalException(retcode, err)

  print 'Configuring database...'
  prompt_db_properties(args)

  #DB setup should be done last after doing any setup.
  
  if is_local_database(args):
    #check if jdbc user is changed
    is_user_changed = is_jdbc_user_changed(args)

    print 'Default properties detected. Using built-in database.'
    store_local_properties(args)

    print 'Checking PostgreSQL...'
    retcode = check_postgre_up()
    if not retcode == 0:
      err = 'Unable to start PostgreSQL server. Exiting'
      raise FatalException(retcode, err)

    print 'Configuring local database...'
    retcode = setup_db(args)
    if not retcode == 0:
      err = 'Running database init script was failed. Exiting.'
      raise FatalException(retcode, err)

    if is_user_changed:
      #remove backup for pg_hba in order to reconfigure postgres
      remove_file(PG_HBA_CONF_FILE_BACKUP)

    print 'Configuring PostgreSQL...'
    retcode = configure_postgres()
    if not retcode == 0:
      err = 'Unable to configure PostgreSQL server. Exiting'
      raise FatalException(retcode, err)

  else:
    retcode = store_remote_properties(args)
    if retcode != 0:
      err = 'Unable to save config file'
      raise FatalException(retcode, err)

    check_jdbc_drivers(args)

    print 'Configuring remote database connection properties...'
    retcode = setup_remote_db(args)
    if retcode == -1:
      err =  "The cli was not found"
      raise NonFatalException(err)

    if not retcode == 0:
      err = 'Error while configuring connection properties. Exiting'
      raise FatalException(retcode, err)
    check_jdbc_drivers(args)

#
# Resets the Ambari Server.
#
def reset(args):
  if not is_root():
    err = 'Ambari-server reset should be run with ' \
          'root-level privileges'
    raise FatalException(4, err)
  choice = get_YN_input("**** WARNING **** You are about to reset and clear the "
                     "Ambari Server database. This will remove all cluster "
                     "host and configuration information from the database. "
                     "You will be required to re-configure the Ambari server "
                     "and re-run the cluster wizard. \n"
                     "Are you SURE you want to perform the reset "
                     "[yes/no]? ", True)
  okToRun = choice

  if not okToRun:
    err =  "Ambari Server 'reset' cancelled"
    raise FatalException(1, err)

  okToRun = get_YN_input("Confirm server reset [yes/no]? ", True)

  if not okToRun:
    err =  "Ambari Server 'reset' cancelled"
    raise FatalException(1, err)

  print "Resetting the Server database..."

  parse_properties_file(args)

  # configure_database_username_password(args)
  if args.persistence_type=="remote":
    client_desc = DATABASE_NAMES[DATABASE_INDEX] + ' ' + DATABASE_CLI_TOOLS_DESC[DATABASE_INDEX]
    client_usage_cmd_drop = DATABASE_CLI_TOOLS_USAGE[DATABASE_INDEX].format(DATABASE_DROP_SCRIPTS[DATABASE_INDEX], args.database_username,
                                                     BLIND_PASSWORD, args.database_name)
    client_usage_cmd_init = DATABASE_CLI_TOOLS_USAGE[DATABASE_INDEX].format(DATABASE_INIT_SCRIPTS[DATABASE_INDEX], args.database_username,
                                                     BLIND_PASSWORD, args.database_name)    

    if get_db_cli_tool(args) != -1:
      retcode, out, err = execute_remote_script(args, DATABASE_DROP_SCRIPTS[DATABASE_INDEX])
      if not retcode == 0:
        if retcode == -1:
          print_warning_msg('Cannot find ' + client_desc + 
                            ' client in the path to reset the Ambari Server ' +
                            'schema. To reset Ambari Server schema ' +
                            'you must run the following DDL against the database ' +
                            'to drop the schema:' + os.linesep + client_usage_cmd_drop 
                            + os.linesep + 'Then you must run the following DDL '
                            + 'against the database to create the schema: ' + os.linesep
                             + client_usage_cmd_init + os.linesep )
        raise NonFatalException(err)

      retcode, out, err = execute_remote_script(args, DATABASE_INIT_SCRIPTS[DATABASE_INDEX])
      if not retcode == 0:
        if retcode == -1:
          print_warning_msg('Cannot find ' + client_desc + ' client in the path to ' +
                            'reset the Ambari Server schema. To reset Ambari Server schema ' +
                            'you must run the following DDL against the database to '
                            + 'drop the schema:' + os.linesep + client_usage_cmd_drop 
                            + os.linesep + 'Then you must run the following DDL ' + 
                            'against the database to create the schema: ' + os.linesep + 
                            client_usage_cmd_init + os.linesep )
        raise NonFatalException(err)

    else:
      err = 'Cannot find ' + client_desc + ' client in the path to reset the Ambari ' +\
      'Server schema. To reset Ambari Server schema ' + \
      'you must run the following DDL against the database to drop the schema:' + \
      os.linesep + client_usage_cmd_drop + os.linesep +   \
      'Then you must run the following DDL against the database to create the ' + \
      'schema: ' + os.linesep + client_usage_cmd_init + os.linesep
      raise NonFatalException(err)

  else:
    dbname = args.database_name
    filename = args.drop_script_file
    username = args.database_username
    password = args.database_password
    command = SETUP_DB_CMD[:]
    command[-1] = command[-1].format(filename, username, password, dbname)
    retcode, outdata, errdata = run_os_command(command)
    if not retcode == 0:
      raise FatalException(1, errdata)

    print_info_msg ("About to run database setup")
    setup_db(args)



#
# Starts the Ambari Server.
#
def start(args):
  current_user = getpass.getuser()
  ambari_user = read_ambari_user()
  if ambari_user is None:
    err = "Unable to detect a system user for Ambari Server. " \
          "Please run \"ambari-server setup\" command to create user "
    raise FatalException(1, err)
  if current_user != ambari_user and not is_root():
    err = "Unable to start Ambari Server as user {0}. Please either run \"ambari-server start\" " \
          "command as root, as sudo or as user \"{1}\"".format(current_user, ambari_user)
    raise FatalException(1, err)

  parse_properties_file(args)
  if os.path.exists(PID_DIR + os.sep + PID_NAME):
    f = open(PID_DIR + os.sep + PID_NAME, "r")
    pid = int(f.readline())
    f.close()
    try:
      os.kill(pid, 0)
      err = "Ambari Server is already running."
      raise FatalException(1, err)
    except OSError as e:
      print_info_msg("Ambari Server is not running...")

  conf_dir = get_conf_dir()
  jdk_path = find_jdk()
  if jdk_path is None:
    err = "No JDK found, please run the \"ambari-server setup\" " \
                    "command to install a JDK automatically or install any " \
                    "JDK manually to " + JDK_INSTALL_DIR
    raise FatalException(1, err)

  # Preparations

  if is_root():
    print "Ambari Server running with 'root' privileges."

    if args.persistence_type == "local":
      retcode = check_postgre_up()
      if not retcode == 0:
        err = "Unable to start PostgreSQL server. Exiting"
        raise FatalException(retcode, err)

    print 'Checking iptables...'
    retcode, out = check_iptables()
    if not retcode == 0 and out == IP_TBLS_ENABLED:
      err = "Failed to stop iptables. Exiting"
      raise FatalException(retcode, err)
  else: # Skipping actions that require root permissions
    print "Unable to check iptables status when starting "\
      "without root privileges."
    print "Please do not forget to disable or adjust iptables if needed"
    if args.persistence_type == "local":
      print "Unable to check PostgreSQL server status when starting " \
            "without root privileges."
      print "Please do not forget to start PostgreSQL server."

  properties = get_ambari_properties()
  isSecure = get_is_secure(properties)
  (isPersisted, masterKeyFile) = get_is_persisted(properties)
  environ = os.environ.copy()
  # Need to handle master key not persisted scenario
  if isSecure and not masterKeyFile:
    prompt = False
    masterKey = environ.get(SECURITY_KEY_ENV_VAR_NAME)

    if masterKey is not None and masterKey != "":
      pass
    else:
      keyLocation = environ.get(SECURITY_MASTER_KEY_LOCATION)

      if keyLocation is not None:
        try:
          # Verify master key can be read by the java process
          with open(keyLocation, 'r') : pass
        except IOError:
          print_warning_msg("Cannot read Master key from path specified in "
                            "environemnt.")
          prompt = True
      else:
        # Key not provided in the environment
        prompt = True

    if prompt:
      masterKey = get_original_master_key(properties)
      tempDir = tempfile.gettempdir()
      tempFilePath = tempDir + os.sep + "masterkey"
      save_master_key(masterKey, tempFilePath, True)
      if ambari_user != current_user:
        uid = pwd.getpwnam(ambari_user).pw_uid
        gid = pwd.getpwnam(ambari_user).pw_gid
        os.chown(tempFilePath, uid, gid)
      else:
        os.chmod(tempFilePath, stat.S_IREAD | stat.S_IWRITE)

      if tempFilePath is not None:
        environ[SECURITY_MASTER_KEY_LOCATION] = tempFilePath

  pidfile = PID_DIR + os.sep + PID_NAME
  command_base = SERVER_START_CMD_DEBUG if (SERVER_DEBUG_MODE or SERVER_START_DEBUG) else SERVER_START_CMD
  command = command_base.format(jdk_path, conf_dir, get_ambari_classpath(), pidfile)
  if is_root() and ambari_user != "root":
    # To inherit exported environment variables (especially AMBARI_PASSPHRASE),
    # from subprocess, we have to skip --login option of su command. That's why
    # we change dir to / (otherwise subprocess can face with 'permission denied'
    # errors while trying to list current directory
    os.chdir("/")
    param_list = ["/bin/su", ambari_user, "-s", "/bin/sh", "-c", command]
  else:
    param_list = ["/bin/sh", "-c", command]

  print_info_msg ("Running server: " + str(param_list))
  server_process = subprocess.Popen(param_list, env=environ)

  print "Server PID at: "+pidfile
  print "Server out at: "+SERVER_OUT_FILE
  print "Server log at: "+SERVER_LOG_FILE


#
# Stops the Ambari Server.
#
def stop(args):
  if (args != None):
    args.exit_message = None
  if os.path.exists(PID_DIR + os.sep + PID_NAME):
    f = open(PID_DIR + os.sep + PID_NAME, "r")
    pid = int(f.readline())
    try:
      os.killpg(os.getpgid(pid), signal.SIGKILL)
    except OSError, e:
      print_info_msg( "Unable to stop Ambari Server - " + str(e) )
      return
    f.close()
    os.remove(f.name)
    print "Ambari Server stopped"
  else:
    print "Ambari Server is not running"



### Stack upgrade ###


def upgrade_stack(args, stack_id):
  if not is_root():
    err = 'Ambari-server upgradestack should be run with ' \
          'root-level privileges'
    raise FatalException(4, err)
  #password access to ambari-server and mapred
  configure_database_username_password(args)
  dbname = args.database_name
  file = args.upgrade_stack_script_file
  stack_name, stack_version = stack_id.split(STACK_NAME_VER_SEP)
  command = UPGRADE_STACK_CMD[:]
  command[-1] = command[-1].format(file, stack_name, stack_version, dbname)
  retcode, outdata, errdata = run_os_command(command)
  if not retcode == 0:
    raise FatalException(retcode, errdata)
  return retcode


#
# Upgrades the Ambari Server.
#
def upgrade(args):
  if not is_root():
    err = 'Ambari-server upgrade should be run with ' \
          'root-level privileges'
    raise FatalException(4, err)

  print 'Updating properties in ' + AMBARI_PROPERTIES_FILE + ' ...'
  retcode = update_ambari_properties()
  if not retcode == 0:
    err = AMBARI_PROPERTIES_FILE + ' file can\'t be updated. Exiting'
    raise FatalException(retcode, err)

  parse_properties_file(args)
  if args.persistence_type == "remote":
    pass
  else:
    print 'Checking PostgreSQL...'
    retcode = check_postgre_up()
    if not retcode == 0:
      err = 'PostgreSQL server not running. Exiting'
      raise FatalException(retcode, err)

    file = args.upgrade_script_file
    print 'Upgrading database...'
    retcode = execute_db_script(args, file)
    if not retcode == 0:
      err = 'Database upgrade script has failed. Exiting.'
      raise FatalException(retcode, err)


    print 'Checking database integrity...'
    check_file = file[:-3] + "Check" + file[-4:]
    retcode = check_db_consistency(args, check_file)

    if not retcode == 0:
      print 'Found inconsistency. Trying to fix...'
      fix_file = file[:-3] + "Fix" + file[-4:]
      retcode = execute_db_script(args, fix_file)

      if not retcode == 0:
        err = 'Database cannot be fixed. Exiting.'
        raise FatalException(retcode, err)
    else:
      print 'Database is consistent.'

  user = read_ambari_user()
  if user is None:
    warn = 'Can not determine custom ambari user. Please run ' \
           '"ambari-server setup" before starting server'
    print_warning_msg(warn)
  else:
    adjust_directory_permissions(user)


#
# The Ambari Server status.
#
def status(args):
  args.exit_message = None
  status, pid = is_server_runing()
  if status:
    print "Ambari Server running"
    print "Found Ambari Server PID: '" + str(pid) + " at: " + PID_DIR + os.sep + PID_NAME
  else:
    print "Ambari Server not running. Stale PID File at: " + PID_DIR + os.sep + PID_NAME



#
# Prints an "info" messsage.
#
def print_info_msg(msg):
  if VERBOSE:
    print("INFO: " + msg)


#
# Prints an "error" messsage.
#
def print_error_msg(msg):
  print("ERROR: " + msg)



#
# Prints a "warning" messsage.
#
def print_warning_msg(msg, bold=False):
  if bold:
    print(BOLD_ON + "WARNING: " + msg + BOLD_OFF)
  else:
    print("WARNING: " + msg)


#
# Gets the y/n input.
#
# return True if 'y' or False if 'n'
#
def get_YN_input(prompt,default):
  yes = set(['yes','ye', 'y'])
  no = set(['no','n'])
  return get_choice_string_input(prompt,default,yes,no)



def get_choice_string_input(prompt,default,firstChoice,secondChoice):
  if SILENT:
    print(prompt)
    return default
  choice = raw_input(prompt).lower()
  if choice in firstChoice:
    return True
  elif choice in secondChoice:
    return False
  elif choice is "": # Just enter pressed
    return default
  else:
    print "input not recognized, please try again: "
    return get_choice_string_input(prompt,default,firstChoice,secondChoice)



def get_validated_string_input(prompt, default, pattern, description,
                               is_pass, allowEmpty=True, validatorFunction=None):

  input = ""
  while not input:
    if SILENT:
      print (prompt)
      input = default
    elif is_pass:
      input = getpass.getpass(prompt)
    else:
      input = raw_input(prompt)
    if not input.strip():
      # Empty input - if default available use default
      if not allowEmpty and not default:
        print 'Property cannot be blank.'
        input = ""
        continue
      else:
        input = default
        if validatorFunction:
          if not validatorFunction(input):
            input = ""
            continue
        break #done here and picking up default
    else:
      if not pattern==None and not re.search(pattern,input.strip()):
        print description
        input= ""
        
      if validatorFunction:
        if not validatorFunction(input):
          input = ""
          continue
  return input


def get_value_from_properties(properties, key, default=""):
  try:
    value = properties.get_property(key)
    if not value:
      value = default
  except:
    return default
  return value

def get_prompt_default(defaultStr=None):
  if not defaultStr or defaultStr == "":
    return ""
  else:
    return '(' + defaultStr + ')'

def setup_ldap():
  if not is_root():
    err = 'Ambari-server setup-ldap should be run with ' \
          'root-level privileges'
    raise FatalException(4, err)

  properties = get_ambari_properties()
  isSecure = get_is_secure(properties)
  # python2.x dict is not ordered
  ldap_property_list_reqd = ["authentication.ldap.primaryUrl",
                        "authentication.ldap.secondaryUrl",
                        "authentication.ldap.useSSL",
                        "authentication.ldap.usernameAttribute",
                        "authentication.ldap.baseDn",
                        "authentication.ldap.bindAnonymously" ]

  ldap_property_list_opt = [ "authentication.ldap.managerDn",
                             LDAP_MGR_PASSWORD_PROPERTY,
                             SSL_TRUSTSTORE_TYPE_PROPERTY,
                             SSL_TRUSTSTORE_PATH_PROPERTY,
                             SSL_TRUSTSTORE_PASSWORD_PROPERTY]

  ldap_property_list_truststore=[SSL_TRUSTSTORE_TYPE_PROPERTY,
                                 SSL_TRUSTSTORE_PATH_PROPERTY,
                                 SSL_TRUSTSTORE_PASSWORD_PROPERTY]

  ldap_property_list_passwords=[LDAP_MGR_PASSWORD_PROPERTY,
                                SSL_TRUSTSTORE_PASSWORD_PROPERTY]

  LDAP_PRIMARY_URL_DEFAULT = get_value_from_properties(properties, ldap_property_list_reqd[0])
  LDAP_SECONDARY_URL_DEFAULT = get_value_from_properties(properties, ldap_property_list_reqd[1])
  LDAP_USE_SSL_DEFAULT = get_value_from_properties(properties, ldap_property_list_reqd[2], "false")
  LDAP_USER_ATT_DEFAULT = get_value_from_properties(properties, ldap_property_list_reqd[3], "uid")
  LDAP_BASE_DN_DEFAULT = get_value_from_properties(properties, ldap_property_list_reqd[4])
  LDAP_BIND_DEFAULT = get_value_from_properties(properties, ldap_property_list_reqd[5], "false")
  LDAP_MGR_DN_DEFAULT = get_value_from_properties(properties, ldap_property_list_opt[0])
  SSL_TRUSTSTORE_TYPE_DEFAULT = get_value_from_properties(properties, SSL_TRUSTSTORE_TYPE_PROPERTY, "jks")
  SSL_TRUSTSTORE_PATH_DEFAULT = get_value_from_properties(properties, SSL_TRUSTSTORE_PATH_PROPERTY)


  ldap_properties_map_reqd =\
  {
    ldap_property_list_reqd[0]:(LDAP_PRIMARY_URL_DEFAULT, "Primary URL* {{host:port}} {0}: ".format(get_prompt_default(LDAP_PRIMARY_URL_DEFAULT)), False),\
    ldap_property_list_reqd[1]:(LDAP_SECONDARY_URL_DEFAULT, "Secondary URL {{host:port}} {0}: ".format(get_prompt_default(LDAP_SECONDARY_URL_DEFAULT)), True),\
    ldap_property_list_reqd[2]:(LDAP_USE_SSL_DEFAULT, "Use SSL* [true/false] {0}: ".format(get_prompt_default(LDAP_USE_SSL_DEFAULT)), False),\
    ldap_property_list_reqd[3]:(LDAP_USER_ATT_DEFAULT, "User name attribute* {0}: ".format(get_prompt_default(LDAP_USER_ATT_DEFAULT)), False),\
    ldap_property_list_reqd[4]:(LDAP_BASE_DN_DEFAULT, "Base DN* {0}: ".format(get_prompt_default(LDAP_BASE_DN_DEFAULT)), False),\
    ldap_property_list_reqd[5]:(LDAP_BIND_DEFAULT, "Bind anonymously* [true/false] {0}: ".format(get_prompt_default(LDAP_BIND_DEFAULT)), False)\
  }

  ldap_property_value_map = {}
  for idx, key in enumerate(ldap_property_list_reqd):
    if idx in [0, 1]:
      pattern = REGEX_HOSTNAME_PORT
    elif idx in [2, 5]:
      pattern = REGEX_TRUE_FALSE
    else:
      pattern = REGEX_ANYTHING
    input = get_validated_string_input(ldap_properties_map_reqd[key][1],
      ldap_properties_map_reqd[key][0], pattern,
      "Invalid characters in the input!", False, ldap_properties_map_reqd[key][2])
    if input is not None and input != "":
      ldap_property_value_map[key] = input

  bindAnonymously = ldap_property_value_map["authentication.ldap.bindAnonymously"]
  anonymous = (bindAnonymously and bindAnonymously.lower() == 'true')
  mgr_password = None
  # Ask for manager credentials only if bindAnonymously is false
  if not anonymous:
    username = get_validated_string_input("Manager DN* {0}: ".format(
      get_prompt_default(LDAP_MGR_DN_DEFAULT)), LDAP_MGR_DN_DEFAULT, ".*",
                "Invalid characters in the input!", False, False)
    ldap_property_value_map[LDAP_MGR_USERNAME_PROPERTY] = username
    mgr_password = configure_ldap_password()
    ldap_property_value_map[LDAP_MGR_PASSWORD_PROPERTY] = mgr_password


  useSSL = ldap_property_value_map["authentication.ldap.useSSL"]
  ldaps = (useSSL and useSSL.lower() == 'true')
  ts_password = None

  if ldaps:
    truststore_default = "n"
    truststore_set = bool(SSL_TRUSTSTORE_PATH_DEFAULT)
    if truststore_set:
      truststore_default = "y"
    custom_trust_store = get_YN_input("Do you want to provide custom TrustStore for Ambari [y/n] ({0})?".
                                      format(truststore_default),
                                      truststore_set)
    if custom_trust_store:
      ts_type = get_validated_string_input(
        "TrustStore type [jks/jceks/pkcs12] {0}:".format(get_prompt_default(SSL_TRUSTSTORE_TYPE_DEFAULT)),
        SSL_TRUSTSTORE_TYPE_DEFAULT,
        "^(jks|jceks|pkcs12)?$", "Wrong type", False)
      ts_path = None
      while True:
        ts_path = get_validated_string_input(
          "Path to TrustStore file {0}:".format(get_prompt_default(SSL_TRUSTSTORE_PATH_DEFAULT)),
          SSL_TRUSTSTORE_PATH_DEFAULT,
          ".*", False, False)
        if os.path.exists(ts_path):
          break
        else:
          print 'File not found.'

      ts_password = read_password("", ".*", "Password for TrustStore:", "Invalid characters in password")

      ldap_property_value_map[SSL_TRUSTSTORE_TYPE_PROPERTY] = ts_type
      ldap_property_value_map[SSL_TRUSTSTORE_PATH_PROPERTY] = ts_path
      ldap_property_value_map[SSL_TRUSTSTORE_PASSWORD_PROPERTY] = ts_password
      pass
    else:
      properties.removeOldProp(SSL_TRUSTSTORE_TYPE_PROPERTY)
      properties.removeOldProp(SSL_TRUSTSTORE_PATH_PROPERTY)
      properties.removeOldProp(SSL_TRUSTSTORE_PASSWORD_PROPERTY)
    pass
  pass

  print '=' * 20
  print 'Review Settings'
  print '=' * 20
  for property in ldap_property_list_reqd:
    if property in ldap_property_value_map:
      print("%s: %s" % (property, ldap_property_value_map[property]))

  for property in ldap_property_list_opt:
    if ldap_property_value_map.has_key(property):
      if property not in ldap_property_list_passwords:
        print("%s: %s" % (property, ldap_property_value_map[property]))
      else:
        print("%s: %s" % (property, BLIND_PASSWORD))

  save_settings = get_YN_input("Save settings [y/n] (y)? ", True)

  if save_settings:
    ldap_property_value_map[CLIENT_SECURITY_KEY] = 'ldap'
    if isSecure:
      if mgr_password:
        encrypted_passwd = encrypt_password(LDAP_MGR_PASSWORD_ALIAS, mgr_password)
        if mgr_password != encrypted_passwd:
          ldap_property_value_map[LDAP_MGR_PASSWORD_PROPERTY] = encrypted_passwd
      pass
      if ts_password:
        encrypted_passwd = encrypt_password(SSL_TRUSTSTORE_PASSWORD_ALIAS, ts_password)
        if ts_password != encrypted_passwd:
          ldap_property_value_map[SSL_TRUSTSTORE_PASSWORD_PROPERTY] = encrypted_passwd
      pass
    pass

    # Persisting values
    update_properties(properties, ldap_property_value_map)
    print 'Saving...done'

  return 0


def read_master_key(isReset=False):
  passwordPattern = ".*"
  passwordPrompt = "Please provide master key for locking the credential store: "
  passwordDescr = "Invalid characters in password. Use only alphanumeric or "\
                  "_ or - characters"
  passwordDefault = ""
  if isReset:
    passwordPrompt = "Enter new Master Key: "

  masterKey = get_validated_string_input(passwordPrompt, passwordDefault,
                            passwordPattern, passwordDescr, True, True)

  if not masterKey:
    print "Master Key cannot be empty!"
    return read_master_key()

  masterKey2 = get_validated_string_input( "Re-enter master key: ",
      passwordDefault, passwordPattern, passwordDescr, True, True)

  if masterKey != masterKey2:
    print "Master key did not match!"
    return read_master_key()

  return masterKey


def encrypt_password(alias, password):
  properties = get_ambari_properties()
  if properties == -1:
    raise FatalException(1, None)
  return get_encrypted_password(alias, password, properties)

def get_encrypted_password(alias, password, properties):
  isSecure = get_is_secure(properties)
  (isPersisted, masterKeyFile) = get_is_persisted(properties)
  if isSecure:
    masterKey = None
    if not masterKeyFile:
      # Encryption enabled but no master key file found
      masterKey = get_original_master_key(properties)

    retCode = save_passwd_for_alias(alias, password, masterKey)
    if retCode != 0:
      print 'Failed to save secure password!'
      return password
    else:
      return get_alias_string(alias)

  return password

def decrypt_password_for_alias(alias):
  properties = get_ambari_properties()
  if properties == -1:
    raise FatalException(1, None)

  isSecure = get_is_secure(properties)
  (isPersisted, masterKeyFile) = get_is_persisted(properties)
  if isSecure:
    masterKey = None
    if not masterKeyFile:
      # Encryption enabled but no master key file found
      masterKey = get_original_master_key(properties)

    return read_passwd_for_alias(alias, masterKey)
  else:
    return alias

def get_original_master_key(properties):
  try:
    masterKey = get_validated_string_input('Enter current Master Key: ',
                                             "", ".*", "", True, False)
  except KeyboardInterrupt:
    print 'Exiting...'
    sys.exit(1)

  # Find an alias that exists
  alias = None
  property = properties.get_property(JDBC_PASSWORD_PROPERTY)
  if property and is_alias_string(property):
    alias = JDBC_RCA_PASSWORD_ALIAS

  if not alias:
    property = properties.get_property(LDAP_MGR_PASSWORD_PROPERTY)
    if property and is_alias_string(property):
      alias = LDAP_MGR_PASSWORD_ALIAS

  if not alias:
    property = properties.get_property(SSL_TRUSTSTORE_PASSWORD_PROPERTY)
    if property and is_alias_string(property):
      alias = SSL_TRUSTSTORE_PASSWORD_ALIAS

  # Decrypt alias with master to validate it, if no master return
  if alias and masterKey:
    password = read_passwd_for_alias(alias, masterKey)
    if not password:
      print "ERROR: Master key does not match."
      return get_original_master_key(properties)

  return masterKey

def get_is_secure(properties):
  isSecure = properties.get_property(SECURITY_IS_ENCRYPTION_ENABLED)
  isSecure = True if isSecure and isSecure.lower() == 'true' else False
  return isSecure

def get_is_persisted(properties):
  keyLocation = get_master_key_location(properties)
  masterKeyFile = search_file(SECURITY_MASTER_KEY_FILENAME, keyLocation)
  isPersisted = True if masterKeyFile else False

  return (isPersisted, masterKeyFile)

def setup_master_key():
  if not is_root():
    err = 'Ambari-server setup should be run with '\
                     'root-level privileges'
    raise FatalException(4, err)

  properties = get_ambari_properties()
  if properties == -1:
    raise FatalException(1, "Failed to read properties file.")

  db_password = properties.get_property(JDBC_PASSWORD_PROPERTY)
  # Encrypt passwords cannot be called before setup
  if not db_password:
    print 'Please call "setup" before "encrypt-passwords". Exiting...'
    return 1

  # Check configuration for location of master key
  isSecure = get_is_secure(properties)
  (isPersisted, masterKeyFile) = get_is_persisted(properties)

  # Read clear text password from file
  if not is_alias_string(db_password) and os.path.isfile(db_password):
    with open(db_password, 'r') as passwdfile:
      db_password = passwdfile.read()
      
  ldap_password = properties.get_property(LDAP_MGR_PASSWORD_PROPERTY)
  ts_password = properties.get_property(SSL_TRUSTSTORE_PASSWORD_PROPERTY)
  resetKey = False
  masterKey = None

  if isSecure:
    print "Password encryption is enabled."
    resetKey = get_YN_input("Do you want to reset Master Key? [y/n] (n): ", False)

  # For encrypting of only unencrypted passwords without resetting the key ask
  # for master key if not persisted.
  if isSecure and not isPersisted and not resetKey:
    print "Master Key not persisted."
    masterKey = get_original_master_key(properties)
  pass

  # Make sure both passwords are clear-text if master key is lost
  if resetKey:
    if not isPersisted:
      print "Master Key not persisted."
      masterKey = get_original_master_key(properties)
      # Unable get the right master key or skipped question <enter>
      if not masterKey:
        print "To disable encryption, do the following:"
        print "- Edit " + find_properties_file() + \
              " and set " + SECURITY_IS_ENCRYPTION_ENABLED + " = " + "false."
        err = "{0} is already encrypted. Please call {1} to store unencrypted" \
              " password and call 'encrypt-passwords' again."
        if db_password and is_alias_string(db_password):
          print err.format('- Database password', "'" + SETUP_ACTION + "'")
        if ldap_password and is_alias_string(ldap_password):
          print err.format('- LDAP manager password', "'" + LDAP_SETUP_ACTION + "'")
        if ts_password and is_alias_string(ts_password):
          print err.format('TrustStore password', "'" + LDAP_SETUP_ACTION + "'")

        return 1
      pass
    pass
  pass

  # Read back any encrypted passwords
  if db_password and is_alias_string(db_password):
    db_password = read_passwd_for_alias(JDBC_RCA_PASSWORD_ALIAS, masterKey)
  if ldap_password and is_alias_string(ldap_password):
    ldap_password = read_passwd_for_alias(LDAP_MGR_PASSWORD_ALIAS, masterKey)
  if ts_password and is_alias_string(ts_password):
    ts_password = read_passwd_for_alias(SSL_TRUSTSTORE_PASSWORD_ALIAS, masterKey)
  # Read master key, if non-secure or reset is true
  if resetKey or not isSecure:
    masterKey = read_master_key(resetKey)
    persist = get_YN_input("Do you want to persist master key. If you choose "\
                           "not to persist, you need to provide the Master "\
                           "Key while starting the ambari server as an env "\
                           "variable named " + SECURITY_KEY_ENV_VAR_NAME +\
                           " or the start will prompt for the master key."
                           " Persist [y/n] (y)? ", True)
    if persist:
      save_master_key(masterKey, get_master_key_location(properties) + os.sep +
                                 SECURITY_MASTER_KEY_FILENAME, persist)
    elif not persist and masterKeyFile:
      try:
        os.remove(masterKeyFile)
        print_info_msg("Deleting master key file at location: " + str(
          masterKeyFile))
      except Exception, e:
        print 'ERROR: Could not remove master key file. %s' % e
    # Blow up the credential store made with previous key, if any
    store_file = get_credential_store_location(properties)
    if os.path.exists(store_file):
      try:
        os.remove(store_file)
      except:
        print_warning_msg("Failed to remove credential store file.")
      pass
    pass
  pass

  propertyMap = {SECURITY_IS_ENCRYPTION_ENABLED : 'true'}
  # Encrypt only un-encrypted passwords
  if db_password and not is_alias_string(db_password):
    retCode = save_passwd_for_alias(JDBC_RCA_PASSWORD_ALIAS, db_password, masterKey)
    if retCode != 0:
      print 'Failed to save secure database password.'
    else:
      propertyMap[JDBC_PASSWORD_PROPERTY] = get_alias_string(JDBC_RCA_PASSWORD_ALIAS)
      remove_password_file(JDBC_PASSWORD_FILENAME)
      if properties.get_property(JDBC_RCA_PASSWORD_FILE_PROPERTY):
        propertyMap[JDBC_RCA_PASSWORD_FILE_PROPERTY] = get_alias_string(JDBC_RCA_PASSWORD_ALIAS)
  pass

  if ldap_password and not is_alias_string(ldap_password):
    retCode = save_passwd_for_alias(LDAP_MGR_PASSWORD_ALIAS, ldap_password, masterKey)
    if retCode != 0:
      print 'Failed to save secure LDAP password.'
    else:
      propertyMap[LDAP_MGR_PASSWORD_PROPERTY] = get_alias_string(LDAP_MGR_PASSWORD_ALIAS)
  pass

  if ts_password and not is_alias_string(ts_password):
    retCode = save_passwd_for_alias(SSL_TRUSTSTORE_PASSWORD_ALIAS, ts_password, masterKey)
    if retCode != 0:
      print 'Failed to save secure TrustStore password.'
    else:
      propertyMap[SSL_TRUSTSTORE_PASSWORD_PROPERTY] = get_alias_string(SSL_TRUSTSTORE_PASSWORD_ALIAS)
  pass

  update_properties(properties, propertyMap)

  # Since files for store and master are created we need to ensure correct
  # permissions
  ambari_user = read_ambari_user()
  if ambari_user:
    adjust_directory_permissions(ambari_user)

  return 0

def get_credential_store_location(properties):
  store_loc = properties[SECURITY_KEYS_DIR]
  if store_loc is None or store_loc == "":
    store_loc = "/var/lib/ambari-server/keys/credentials.jceks"
  else:
    store_loc += os.sep + "credentials.jceks"
  return store_loc

def get_master_key_location(properties):
  keyLocation = properties[SECURITY_MASTER_KEY_LOCATION]
  if keyLocation is None or keyLocation == "":
    keyLocation = properties[SECURITY_KEYS_DIR]
  return keyLocation

def is_alias_string(passwdStr):
  regex = re.compile("\$\{alias=[\w\.]+\}")
  # Match implies string at beginning of word
  r = regex.match(passwdStr)
  if r is not None:
    return True
  else:
    return False

def get_alias_string(alias):
  return "${alias=" + alias + "}"

def get_alias_from_alias_string(aliasStr):
  return aliasStr[8:-1]

def read_passwd_for_alias(alias, masterKey=""):
  if alias:
    jdk_path = find_jdk()
    if jdk_path is None:
      print_error_msg("No JDK found, please run the \"setup\" "
                      "command to install a JDK automatically or install any "
                      "JDK manually to " + JDK_INSTALL_DIR)
      return 1

    tempFileName = "ambari.passwd"
    passwd = ""
    tempDir = tempfile.gettempdir()
    #create temporary file for writing
    tempFilePath = tempDir + os.sep + tempFileName
    file = open(tempFilePath, 'w+')
    os.chmod(tempFilePath, stat.S_IREAD | stat.S_IWRITE)
    file.close()

    if masterKey is None or masterKey == "":
      masterKey = "None"

    command = SECURITY_PROVIDER_GET_CMD.format(jdk_path,
      get_conf_dir(), get_ambari_classpath(), alias, tempFilePath, masterKey)
    (retcode, stdout, stderr) = run_os_command(command)
    print_info_msg("Return code from credential provider get passwd: " +
                   str(retcode))
    if retcode != 0:
      print 'ERROR: Unable to read password from store. alias = ' + alias
    else:
      passwd = open(tempFilePath, 'r').read()
      # Remove temporary file
    os.remove(tempFilePath)
    return passwd
  else:
    print_error_msg("Alias is unreadable.")

def save_passwd_for_alias(alias, passwd, masterKey=""):
  if alias and passwd:
    jdk_path = find_jdk()
    if jdk_path is None:
      print_error_msg("No JDK found, please run the \"setup\" "
                      "command to install a JDK automatically or install any "
                      "JDK manually to " + JDK_INSTALL_DIR)
      return 1

    if masterKey is None or masterKey == "":
      masterKey = "None"

    command = SECURITY_PROVIDER_PUT_CMD.format(jdk_path, get_conf_dir(),
      get_ambari_classpath(), alias, passwd, masterKey)
    (retcode, stdout, stderr) = run_os_command(command)
    print_info_msg("Return code from credential provider save passwd: " +
                   str(retcode))
    return retcode
  else:
    print_error_msg("Alias or password is unreadable.")

def save_master_key(master_key, key_location, persist=True):
  if master_key:
    jdk_path = find_jdk()
    if jdk_path is None:
      print_error_msg("No JDK found, please run the \"setup\" "
                      "command to install a JDK automatically or install any "
                      "JDK manually to " + JDK_INSTALL_DIR)
      return 1
    command = SECURITY_PROVIDER_KEY_CMD.format(jdk_path,
      get_ambari_classpath(), get_conf_dir(), master_key, key_location, persist)
    (retcode, stdout, stderr) = run_os_command(command)
    print_info_msg("Return code from credential provider save KEY: " +
                   str(retcode))
  else:
    print_error_msg("Master key cannot be None.")


def configure_ldap_password():
  passwordDefault = ""
  passwordPrompt = 'Enter Manager Password* : '
  passwordPattern = ".*"
  passwordDescr = "Invalid characters in password."

  password = read_password(passwordDefault, passwordPattern, passwordPrompt,
    passwordDescr)

  return password

# Copy file to /tmp and save with file.# (largest # is latest file)
def backup_file_in_temp(filePath):
  if filePath is not None:
    tmpDir = tempfile.gettempdir()
    back_up_file_count = len(glob.glob1(tmpDir, AMBARI_PROPERTIES_FILE + "*"))
    try:
      shutil.copyfile(filePath, tmpDir + os.sep +
                                AMBARI_PROPERTIES_FILE + "." + str(back_up_file_count + 1))
    except (Exception), e:
      print_error_msg('Could not backup file in temp "%s": %s' % (str(
        back_up_file_count, e)))
  return 0

# update properties in a section-less properties file
# Cannot use ConfigParser due to bugs in version 2.6
def update_properties(propertyMap):
  conf_file = search_file(AMBARI_PROPERTIES_FILE, get_conf_dir())
  backup_file_in_temp(conf_file)
  if propertyMap is not None and conf_file is not None:
    properties = Properties()
    try:
      with open(conf_file, 'r') as file:
        properties.load(file)
    except (Exception), e:
      print_error_msg ('Could not read "%s": %s' % (conf_file, e))
      return -1

    #for key in propertyMap.keys():
      #properties[key] = propertyMap[key]
    for key in propertyMap.keys():
      properties.removeOldProp(key)
      properties.process_pair(key, str(propertyMap[key]))

    with open(conf_file, 'w') as file:
      properties.store(file)

  return 0

def update_properties(properties, propertyMap):
  conf_file = search_file(AMBARI_PROPERTIES_FILE, get_conf_dir())
  backup_file_in_temp(conf_file)
  if conf_file is not None:
    if propertyMap is not None:
      for key in propertyMap.keys():
        properties.removeOldProp(key)
        properties.process_pair(key, str(propertyMap[key]))
      pass

    with open(conf_file, 'w') as file:
      properties.store(file)
    pass
  pass

def setup_https(args):
  if not is_root():
    err = 'ambari-server setup-https should be run with ' \
          'root-level privileges'
    raise FatalException(4, err)
  args.exit_message = None
  if not SILENT:
    properties = get_ambari_properties()
    try:
      security_server_keys_dir = properties.get_property(SSL_KEY_DIR)
      client_api_ssl_port = DEFAULT_SSL_API_PORT if properties.get_property(SSL_API_PORT) in ("")\
                            else properties.get_property(SSL_API_PORT)
      api_ssl = properties.get_property(SSL_API) in ['true']
      cert_was_imported = False
      cert_must_import = True
      if api_ssl:
       if get_YN_input("Do you want to disable HTTPS [y/n] (n)? ", False):
        properties.process_pair(SSL_API, "false")
        cert_must_import=False
       else:
        properties.process_pair(SSL_API_PORT, \
                                get_validated_string_input(\
                                "SSL port ["+str(client_api_ssl_port)+"] ? ",\
                                str(client_api_ssl_port),\
                                "^[0-9]{1,5}$", "Invalid port.", False, validatorFunction = is_valid_https_port))
        cert_was_imported = import_cert_and_key_action(security_server_keys_dir, properties)
      else:
       if get_YN_input("Do you want to configure HTTPS [y/n] (y)? ", True):
        properties.process_pair(SSL_API_PORT,\
        get_validated_string_input("SSL port ["+str(client_api_ssl_port)+"] ? ",\
        str(client_api_ssl_port), "^[0-9]{1,5}$", "Invalid port.", False, validatorFunction = is_valid_https_port))
        cert_was_imported = import_cert_and_key_action(security_server_keys_dir, properties)
       else:
        return
      
      if cert_must_import and not cert_was_imported:
        print 'Setup of HTTPS failed. Exiting.'
        return

      conf_file = find_properties_file()
      f = open(conf_file, 'w')
      properties.store(f, "Changed by 'ambari-server setup-https' command")

      ambari_user = read_ambari_user()
      if ambari_user:
        adjust_directory_permissions(ambari_user)
    except (KeyError), e:
      err = 'Property ' + str(e) + ' is not defined at ' + conf_file
      raise FatalException(1, err)
  else:
    warning = "setup-https is not enabled in silent mode."
    raise NonFatalException(warning)


def is_server_runing():
  if os.path.exists(PID_DIR + os.sep + PID_NAME):
    f = open(PID_DIR + os.sep + PID_NAME, "r")
    pid = int(f.readline())
    f.close()
    retcode, out, err = run_os_command("ps -p " + str(pid))
    if retcode == 0:
      return True, pid
    else:
      return False, None
  else:
    return False, None
 

def setup_component_https(component, command, property, alias):

  if not SILENT:

    jdk_path = find_jdk()
    if jdk_path is None:
      err = "No JDK found, please run the \"ambari-server setup\" " \
                      "command to install a JDK automatically or install any " \
                      "JDK manually to " + JDK_INSTALL_DIR
      raise FatalException(1, err)

    properties = get_ambari_properties()

    use_https = properties.get_property(property) in ['true']

    if use_https:
      if get_YN_input("Do you want to disable HTTPS for " + component + " [y/n] (n)? ", False):

        truststore_path     = get_truststore_path(properties)
        truststore_password = get_truststore_password(properties)

        run_component_https_cmd(get_delete_cert_command(jdk_path, alias, truststore_path, truststore_password))

        properties.process_pair(property, "false")

      else:
        return
    else:
      if get_YN_input("Do you want to configure HTTPS for " + component + " [y/n] (y)? ", True):

        truststore_type     = get_truststore_type(properties)
        truststore_path     = get_truststore_path(properties)
        truststore_password = get_truststore_password(properties)
        
        run_os_command(get_delete_cert_command(jdk_path, alias, truststore_path, truststore_password))

        import_cert_path = get_validated_filepath_input(\
                          "Enter path to " + component + " Certificate: ",\
                          "Certificate not found")

        run_component_https_cmd(get_import_cert_command(jdk_path, alias, truststore_type, import_cert_path, truststore_path, truststore_password))

        properties.process_pair(property, "true")

      else:
        return

    conf_file = find_properties_file()
    f = open(conf_file, 'w')
    properties.store(f, "Changed by 'ambari-server " + command + "' command")

  else:
    print command + " is not enabled in silent mode."

def get_truststore_type(properties):

  truststore_type = properties.get_property(SSL_TRUSTSTORE_TYPE_PROPERTY)
  if not truststore_type:
    SSL_TRUSTSTORE_TYPE_DEFAULT = get_value_from_properties(properties, SSL_TRUSTSTORE_TYPE_PROPERTY, "jks")

    truststore_type = get_validated_string_input(
      "TrustStore type [jks/jceks/pkcs12] {0}:".format(get_prompt_default(SSL_TRUSTSTORE_TYPE_DEFAULT)),
      SSL_TRUSTSTORE_TYPE_DEFAULT,
      "^(jks|jceks|pkcs12)?$", "Wrong type", False)

    if truststore_type:
      properties.process_pair(SSL_TRUSTSTORE_TYPE_PROPERTY, truststore_type)

  return truststore_type

def get_truststore_path(properties):

  truststore_path = properties.get_property(SSL_TRUSTSTORE_PATH_PROPERTY)
  if not truststore_path:
    SSL_TRUSTSTORE_PATH_DEFAULT = get_value_from_properties(properties, SSL_TRUSTSTORE_PATH_PROPERTY)

    while not truststore_path:
      truststore_path = get_validated_string_input(
        "Path to TrustStore file {0}:".format(get_prompt_default(SSL_TRUSTSTORE_PATH_DEFAULT)),
        SSL_TRUSTSTORE_PATH_DEFAULT,
        ".*", False, False)

    if truststore_path:
      properties.process_pair(SSL_TRUSTSTORE_PATH_PROPERTY, truststore_path)

  return truststore_path

def get_truststore_password(properties):
  truststore_password = properties.get_property(SSL_TRUSTSTORE_PASSWORD_PROPERTY)
  isSecure = get_is_secure(properties)
  if truststore_password:
    if isSecure:
      truststore_password = decrypt_password_for_alias(SSL_TRUSTSTORE_PASSWORD_ALIAS)
  else:
    truststore_password = read_password("", ".*", "Password for TrustStore:", "Invalid characters in password")
    if truststore_password:
      encrypted_password = get_encrypted_password(SSL_TRUSTSTORE_PASSWORD_ALIAS, truststore_password, properties)
      properties.process_pair(SSL_TRUSTSTORE_PASSWORD_PROPERTY, encrypted_password)

  return truststore_password

def run_component_https_cmd(cmd):
  retcode, out, err = run_os_command(cmd)

  if not retcode == 0:
    err = 'Error occured during truststore setup ! :' + out + " : " + err
    raise FatalException(1, err)
    
def get_delete_cert_command(jdk_path, alias, truststore_path, truststore_password):
  cmd = KEYTOOL_DELETE_CERT_CMD.format(jdk_path, alias, truststore_password)
  if truststore_path:
    cmd += KEYTOOL_KEYSTORE.format(truststore_path)
  return cmd
    
def get_import_cert_command(jdk_path, alias, truststore_type, import_cert_path, truststore_path, truststore_password):
  cmd = KEYTOOL_IMPORT_CERT_CMD.format(jdk_path, alias, truststore_type, import_cert_path, truststore_password)
  if truststore_path:
    cmd += KEYTOOL_KEYSTORE.format(truststore_path)
  return cmd

def import_cert_and_key_action(security_server_keys_dir, properties):
  if import_cert_and_key(security_server_keys_dir):
   properties.process_pair(SSL_SERVER_CERT_NAME, SSL_CERT_FILE_NAME)
   properties.process_pair(SSL_SERVER_KEY_NAME, SSL_KEY_FILE_NAME)
   properties.process_pair(SSL_API, "true")
   return True
  else:
   return False
   
def import_cert_and_key(security_server_keys_dir):
  import_cert_path = get_validated_filepath_input(\
                    "Enter path to Certificate: ",\
                    "Certificate not found")
  import_key_path  =  get_validated_filepath_input(\
                      "Enter path to Private Key: ", "Private Key not found")
  pem_password = get_validated_string_input("Please enter password for Private Key: ", "", None, None, True)
  
  certInfoDict = get_cert_info(import_cert_path)
  
  if not certInfoDict:
    print_warning_msg('Unable to get Certificate information')
  else:  
    #Validate common name of certificate
    if not is_valid_cert_host(certInfoDict):
      print_warning_msg('Unable to validate Certificate hostname')
  
    #Validate issue and expirations dates of certificate
    if not is_valid_cert_exp(certInfoDict):
      print_warning_msg('Unable to validate Certificate issue and expiration dates')

  #jetty requires private key files with non-empty key passwords
  retcode = 0
  err = ''
  if not pem_password:
    print 'Generating random password for HTTPS keystore...done.'
    pem_password = generate_random_string()
    retcode, out, err = run_os_command(CHANGE_KEY_PWD_CND.format(
      import_key_path, pem_password))
    import_key_path += '.secured'

  if retcode == 0:
    keystoreFilePath = os.path.join(security_server_keys_dir,\
                                    SSL_KEYSTORE_FILE_NAME)
    keystoreFilePathTmp = os.path.join(tempfile.gettempdir(),\
                                       SSL_KEYSTORE_FILE_NAME)
    passFilePath = os.path.join(security_server_keys_dir,\
                                SSL_KEY_PASSWORD_FILE_NAME)
    passFilePathTmp = os.path.join(tempfile.gettempdir(),\
      SSL_KEY_PASSWORD_FILE_NAME)
    passinFilePath = os.path.join(tempfile.gettempdir(),\
                                   SSL_PASSIN_FILE)
    passwordFilePath = os.path.join(tempfile.gettempdir(),\
                                   SSL_PASSWORD_FILE)
  
    with open(passFilePathTmp, 'w+') as passFile:
      passFile.write(pem_password)
      passFile.close
      pass
   
    set_file_permissions(passFilePath, "660", read_ambari_user(), False)
 
    copy_file(passFilePathTmp, passinFilePath)
    copy_file(passFilePathTmp, passwordFilePath)
 
    retcode, out, err = run_os_command(EXPRT_KSTR_CMD.format(import_cert_path,\
    import_key_path, passwordFilePath, passinFilePath, keystoreFilePathTmp))
  if retcode == 0:
   print 'Importing and saving Certificate...done.'
   import_file_to_keystore(keystoreFilePathTmp, keystoreFilePath)
   import_file_to_keystore(passFilePathTmp, passFilePath)

   import_file_to_keystore(import_cert_path, os.path.join(\
                          security_server_keys_dir, SSL_CERT_FILE_NAME))
   import_file_to_keystore(import_key_path, os.path.join(\
                          security_server_keys_dir, SSL_KEY_FILE_NAME))

   #Validate keystore
   retcode, out, err = run_os_command(VALIDATE_KEYSTORE_CMD.format(keystoreFilePath,\
   passwordFilePath, passinFilePath))
   
   remove_file(passinFilePath)
   remove_file(passwordFilePath)

   if not retcode == 0:
     print 'Error during keystore validation occured!:'
     print err
     return False
   
   return True
  else:
   print_error_msg('Could not import Certificate and Private Key.')
   print 'SSL error on exporting keystore: ' + err.rstrip() + \
         '.\nPlease ensure that provided Private Key password is correct and ' +\
         're-import Certificate.'

   return False
 
def import_file_to_keystore(source, destination):
  shutil.copy(source, destination)
  set_file_permissions(destination, "660", read_ambari_user(), False)

def generate_random_string(length=SSL_KEY_PASSWORD_LENGTH):
  chars = string.digits + string.ascii_letters
  return ''.join(random.choice(chars) for x in range(length))
 
def get_validated_filepath_input(prompt, description, default=None):
  input = False
  while not input:
    if SILENT:
      print (prompt)
      return default
    else:
      input = raw_input(prompt)
      if not input==None:
        input = input.strip()
      if not input==None and not ""==input and os.path.exists(input):
        return input
      else:
        print description
        input=False


def get_cert_info(path):
  retcode, out, err = run_os_command(GET_CRT_INFO_CMD.format(path))
  
  if retcode != 0:
    print 'Error getting Certificate info'
    print err
    return None
  
  if out:
    certInfolist = out.split(os.linesep)
  else:
    print 'Empty Certificate info'
    return None
  
  notBefore = None
  notAfter = None
  subject = None
  
  for item in range(len(certInfolist)):
      
    if certInfolist[item].startswith('notAfter='):
      notAfter = certInfolist[item].split('=')[1]

    if certInfolist[item].startswith('notBefore='):
      notBefore = certInfolist[item].split('=')[1]
      
    if certInfolist[item].startswith('subject='):
      subject = certInfolist[item].split('=', 1)[1]
      
  #Convert subj to dict
  pattern = re.compile(r"[A-Z]{1,2}=[\w.-]{1,}")
  if subject:
    subjList = pattern.findall(subject)
    keys = [item.split('=')[0] for item in subjList]
    values = [item.split('=')[1] for item in subjList]
    subjDict = dict(zip(keys, values))
  
    result = subjDict
    result['notBefore'] = notBefore
    result['notAfter'] = notAfter
    result['subject'] = subject
  
    return result
  else:
    return {}

def is_valid_cert_exp(certInfoDict):
  if certInfoDict.has_key(NOT_BEFORE_ATTR):
    notBefore = certInfoDict[NOT_BEFORE_ATTR]
  else:
    print_warning_msg('There is no Not Before value in Certificate')
    return False

  if certInfoDict.has_key(NOT_AFTER_ATTR):
    notAfter = certInfoDict['notAfter']
  else:
    print_warning_msg('There is no Not After value in Certificate')
    return False
      
  
  notBeforeDate = datetime.datetime.strptime(notBefore, SSL_DATE_FORMAT)
  notAfterDate = datetime.datetime.strptime(notAfter, SSL_DATE_FORMAT)
  
  currentDate = datetime.datetime.now()
  
  if currentDate > notAfterDate:
    print_warning_msg('Certificate expired on: ' + str(notAfterDate))
    return False
    
  if currentDate < notBeforeDate:
    print_warning_msg('Certificate will be active from: ' + str(notBeforeDate))
    return False

  return True

def is_valid_cert_host(certInfoDict):
  if certInfoDict.has_key(COMMON_NAME_ATTR):
   commonName = certInfoDict[COMMON_NAME_ATTR]
  else:
    print_warning_msg('There is no Common Name in Certificate')
    return False

  fqdn = get_fqdn()

  if not fqdn:
    print_warning_msg('Failed to get server FQDN')
    return False
  
  if commonName != fqdn:
    print_warning_msg('Common Name in Certificate: ' + commonName + ' does not match the server FQDN: ' + fqdn)
    return False

  return True
  
def is_valid_https_port(port):
  properties = get_ambari_properties()
  if properties == -1:
    print "Error getting ambari properties"
    return False

  one_way_port = properties[SRVR_ONE_WAY_SSL_PORT_PROPERTY]
  if not one_way_port:
    one_way_port = SRVR_ONE_WAY_SSL_PORT

  two_way_port = properties[SRVR_TWO_WAY_SSL_PORT_PROPERTY]
  if not two_way_port:
    two_way_port = SRVR_TWO_WAY_SSL_PORT

  if port.strip() == one_way_port.strip():
    print "Port for https can't match the port for one way authentication port(" + one_way_port + ")"
    return False

  if port.strip() == two_way_port.strip():
    print "Port for https can't match the port for two way authentication port(" + two_way_port + ")"
    return False

  return True

def get_fqdn():
  properties = get_ambari_properties()
  if properties == -1:
    print "Error reading ambari properties"
    return None

  get_fqdn_service_url = properties[GET_FQDN_SERVICE_URL]
  try:
    handle = urllib2.urlopen(get_fqdn_service_url, '', 2)
    str = handle.read()
    handle.close()
    return str
  except Exception, e:
    return socket.getfqdn()

#
# Main.
#
def main():
  parser = optparse.OptionParser(usage="usage: %prog [options] action [stack_id]",)

  parser.add_option('-f', '--init-script-file',
                      default='/var/lib/ambari-server/'
                              'resources/Ambari-DDL-Postgres-CREATE.sql',
                      help="File with setup script")
  parser.add_option('-r', '--drop-script-file', default="/var/lib/"
                              "ambari-server/resources/"
                              "Ambari-DDL-Postgres-DROP.sql",
                      help="File with drop script")
  parser.add_option('-u', '--upgrade-script-file', default="/var/lib/"
                              "ambari-server/resources/upgrade/ddl/"
                              "Ambari-DDL-Postgres-UPGRADE-1.3.0.sql",
                      help="File with upgrade script")
  parser.add_option('-t', '--upgrade-stack-script-file', default="/var/lib/"
                              "ambari-server/resources/upgrade/dml/"
                              "Ambari-DML-Postgres-UPGRADE_STACK.sql",
                      help="File with stack upgrade script")
  parser.add_option('-j', '--java-home', default=None,
                  help="Use specified java_home.  Must be valid on all hosts")
  parser.add_option('-i', '--jdk-location', dest="jdk_location", default=None,
                    help="Use specified JDK file in local filesystem instead of downloading")
  parser.add_option('-c', '--jce-policy', default=None,
                  help="Use specified jce_policy.  Must be valid on all hosts", dest="jce_policy") 
  parser.add_option("-v", "--verbose",
                  action="store_true", dest="verbose", default=False,
                  help="Print verbose status messages")
  parser.add_option("-s", "--silent",
                  action="store_true", dest="silent", default=False,
                  help="Silently accepts default prompt values")
  parser.add_option('-g', '--debug', action="store_true", dest='debug', default=False,
                    help="Start ambari-server in debug mode")

  parser.add_option('--database', default=None, help ="Database to use postgres|oracle", dest="database")
  parser.add_option('--databasehost', default=None, help="Hostname of database server", dest="database_host")
  parser.add_option('--databaseport', default=None, help="Database port", dest="database_port")
  parser.add_option('--databasename', default=None, help="Database/Schema/Service name or ServiceID",
                    dest="database_name")
  parser.add_option('--databaseusername', default=None, help="Database user login", dest="database_username")
  parser.add_option('--databasepassword', default=None, help="Database user password", dest="database_password")
  parser.add_option('--sidorsname', default="sname", help="Oracle database identifier type, Service ID/Service "
                                                         "Name sid|sname", dest="sid_or_sname")

  (options, args) = parser.parse_args()

  # set verbose
  global VERBOSE
  VERBOSE = options.verbose

  # set silent
  global SILENT
  SILENT = options.silent

  # debug mode
  global SERVER_DEBUG_MODE
  SERVER_DEBUG_MODE = options.debug

  global DATABASE_INDEX
  global PROMPT_DATABASE_OPTIONS
  #perform checks

  options.warnings = []

  if options.database is None \
    and options.database_host is None \
    and options.database_port is None \
    and options.database_name is None \
    and options.database_username is None \
    and options.database_password is None:

    PROMPT_DATABASE_OPTIONS = True

  elif not (options.database is not None
    and options.database_host is not None
    and options.database_port is not None
    and options.database_name is not None
    and options.database_username is not None
    and options.database_password is not None):
    parser.error('All database options should be set. Please see help for the options.')

  #correct database
  if options.database is not None and options.database not in DATABASE_NAMES:
    parser.print_help()
    parser.error("Unsupported Database " + options.database)
  elif options.database is not None:
    options.database = options.database.lower()
    DATABASE_INDEX = DATABASE_NAMES.index(options.database)

  #correct port
  if options.database_port is not None:
    correct=False
    try:
      port = int(options.database_port)
      if 65536 > port > 0:
        correct = True
    except ValueError:
      pass
    if not correct:
      parser.print_help()
      parser.error("Incorrect database port " + options.database_port)

  if options.database is not None and options.database == "postgres":
    print "WARNING: HostName for postgres server " + options.database_host + \
     " will be ignored: using localhost."
    options.database_host = "localhost"

  if options.sid_or_sname.lower() not in ["sid", "sname"]:
    print "WARNING: Valid values for sid_or_sname are 'sid' or 'sname'. Use 'sid' if the db identifier type is " \
          "Service ID. Use 'sname' if the db identifier type is Service Name"
    parser.print_help()
    exit(-1)
  else:
    options.sid_or_sname = options.sid_or_sname.lower()

  if len(args) == 0:
    print parser.print_help()
    parser.error("No action entered")

  action = args[0]

  if action == UPGRADE_STACK_ACTION:
    args_number_required = 2
  else:
    args_number_required = 1

  if len(args) < args_number_required:
    print parser.print_help()
    parser.error("Invalid number of arguments. Entered: " + str(len(args)) + ", required: " + str(args_number_required))

  options.exit_message = "Ambari Server '%s' completed successfully." % action
  try:
    if action == SETUP_ACTION:
      setup(options)
    elif action == START_ACTION:
      start(options)
    elif action == STOP_ACTION:
      stop(options)
    elif action == RESET_ACTION:
      reset(options)
    elif action == STATUS_ACTION:
      status(options)
    elif action == UPGRADE_ACTION:
      upgrade(options)
    elif action == UPGRADE_STACK_ACTION:
      stack_id = args[1]
      upgrade_stack(options, stack_id)
    elif action == LDAP_SETUP_ACTION:
      setup_ldap()
    elif action == ENCRYPT_PASSWORDS_ACTION:
      setup_master_key()
    elif action == UPDATE_METAINFO_ACTION:
      update_metainfo(options)
    elif action == SETUP_HTTPS_ACTION:
      setup_https(options)
    elif action == SETUP_GANGLIA_HTTPS_ACTION:
      setup_component_https("Ganglia", "setup-ganglia-https", GANGLIA_HTTPS, "ganglia_cert")
    elif action == SETUP_NAGIOS_HTTPS_ACTION:
      setup_component_https("Nagios", "setup-nagios-https", NAGIOS_HTTPS, "nagios_cert")
    else:
      parser.error("Invalid action")

    if action in ACTION_REQUIRE_RESTART:
      if is_server_runing():
        print 'NOTE: Restart Ambari Server to apply changes'+ \
              ' ("ambari-server restart|stop|start")'

  except FatalException as e:
    if e.reason is not None:
      print_error_msg("Exiting with exit code {0}. Reason: {1}".format(e.code, e.reason))
    sys.exit(e.code)
  except NonFatalException as e:
    options.exit_message = "Ambari Server '%s' completed with warnings." % action
    if e.reason is not None:
      print_warning_msg(e.reason)

  if options.exit_message is not None:
    print options.exit_message


# A Python replacement for java.util.Properties
# Based on http://code.activestate.com/recipes
# /496795-a-python-replacement-for-javautilproperties/
class Properties(object):
  def __init__(self, props=None):
    self._props = {}
    self._origprops = {}
    self._keymap = {}

    self.othercharre = re.compile(r'(?<!\\)(\s*\=)|(?<!\\)(\s*\:)')
    self.othercharre2 = re.compile(r'(\s*\=)|(\s*\:)')
    self.bspacere = re.compile(r'\\(?!\s$)')

  def __parse(self, lines):
    lineno = 0
    i = iter(lines)
    for line in i:
      lineno += 1
      line = line.strip()
      if not line: continue
      if line[0] == '#': continue
      escaped = False
      sepidx = -1
      flag = 0
      m = self.othercharre.search(line)
      if m:
        first, last = m.span()
        start, end = 0, first
        flag = 1
        wspacere = re.compile(r'(?<![\\\=\:])(\s)')
      else:
        if self.othercharre2.search(line):
          wspacere = re.compile(r'(?<![\\])(\s)')
        start, end = 0, len(line)
      m2 = wspacere.search(line, start, end)
      if m2:
        first, last = m2.span()
        sepidx = first
      elif m:
        first, last = m.span()
        sepidx = last - 1
      while line[-1] == '\\':
        nextline = i.next()
        nextline = nextline.strip()
        lineno += 1
        line = line[:-1] + nextline
      if sepidx != -1:
        key, value = line[:sepidx], line[sepidx + 1:]
      else:
        key, value = line, ''
      self.process_pair(key, value)

  def process_pair(self, key, value):
    oldkey = key
    oldvalue = value
    keyparts = self.bspacere.split(key)
    strippable = False
    lastpart = keyparts[-1]
    if lastpart.find('\\ ') != -1:
      keyparts[-1] = lastpart.replace('\\', '')
    elif lastpart and lastpart[-1] == ' ':
      strippable = True
    key = ''.join(keyparts)
    if strippable:
      key = key.strip()
      oldkey = oldkey.strip()
    oldvalue = self.unescape(oldvalue)
    value = self.unescape(value)
    self._props[key] = None if value is None else value.strip()
    if self._keymap.has_key(key):
      oldkey = self._keymap.get(key)
      self._origprops[oldkey] = None if oldvalue is None else oldvalue.strip()
    else:
      self._origprops[oldkey] = None if oldvalue is None else oldvalue.strip()
      self._keymap[key] = oldkey

  
  def unescape(self, value):
    newvalue = value
    if not value is None:
     newvalue = value.replace('\:', ':')
     newvalue = newvalue.replace('\=', '=')
    return newvalue

  def removeOldProp(self, key):
    if self._origprops.has_key(key):
      del self._origprops[key]
    pass
  
  def load(self, stream):
    if type(stream) is not file:
      raise TypeError, 'Argument should be a file object!'
    if stream.mode != 'r':
      raise ValueError, 'Stream should be opened in read-only mode!'
    try:
      self.fileName = os.path.abspath(stream.name)
      lines = stream.readlines()
      self.__parse(lines)
    except IOError, e:
      raise

  def get_property(self, key):
    return self._props.get(key, '')

  def propertyNames(self):
    return self._props.keys()

  def getPropertyDict(self):
    return self._props

  def __getitem__(self, name):
    return self.get_property(name)

  def __getattr__(self, name):
    try:
      return self.__dict__[name]
    except KeyError:
      if hasattr(self._props, name):
        return getattr(self._props, name)

  def store(self, out, header=""):
    """ Write the properties list to the stream 'out' along
    with the optional 'header' """
    if out.mode[0] != 'w':
      raise ValueError,'Steam should be opened in write mode!'
    try:
      out.write(''.join(('#', ASF_LICENSE_HEADER, '\n')))
      out.write(''.join(('#',header,'\n')))
      # Write timestamp
      tstamp = time.strftime('%a %b %d %H:%M:%S %Z %Y', time.localtime())
      out.write(''.join(('#',tstamp,'\n')))
      # Write properties from the pristine dictionary
      for prop, val in self._origprops.items():
        if val is not None:
          out.write(''.join((prop,'=',val,'\n')))
      out.close()
    except IOError, e:
      raise

if __name__ == "__main__":
  try:
    main() 
  except (KeyboardInterrupt, EOFError):
    print("\nAborting ... Keyboard Interrupt.")
    sys.exit(1)
