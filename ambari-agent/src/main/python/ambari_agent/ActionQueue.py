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

import logging
import traceback
import threading
from threading import Thread
import pprint
import os

from LiveStatus import LiveStatus
from shell import shellRunner
import PuppetExecutor
import UpgradeExecutor
import PythonExecutor
from ActualConfigHandler import ActualConfigHandler
from ActionDependencyManager import ActionDependencyManager
from CommandStatusDict import CommandStatusDict


logger = logging.getLogger()
installScriptHash = -1

class ActionQueue(threading.Thread):
  """ Action Queue for the agent. We pick one command at a time from the queue
  and execute it
  Note: Action and command terms in this and related classes are used interchangeably
  """

  # How many actions can be performed in parallel. Feel free to change
  MAX_CONCURRENT_ACTIONS = 5

  STATUS_COMMAND = 'STATUS_COMMAND'
  EXECUTION_COMMAND = 'EXECUTION_COMMAND'
  ROLE_COMMAND_UPGRADE = 'UPGRADE'

  IN_PROGRESS_STATUS = 'IN_PROGRESS'

  def __init__(self, config, controller):
    super(ActionQueue, self).__init__()
    self.commandQueue = ActionDependencyManager(config)
    self.commandStatuses = CommandStatusDict(callback_action =
      self.status_update_callback)
    self.config = config
    self.controller = controller
    self.sh = shellRunner()
    self._stop = threading.Event()
    self.tmpdir = config.get('agent', 'prefix')

  def stop(self):
    self._stop.set()

  def stopped(self):
    return self._stop.isSet()

  def put(self, commands):
    self.commandQueue.put_actions(commands)


  def run(self):
    while not self.stopped():
      # Taking a new portion of tasks
      portion = self.commandQueue.get_next_action_group() # Will block if queue is empty
      portion = portion[::-1] # Reverse list order
      self.process_portion_of_actions(portion)


  def process_portion_of_actions(self, portion):
    # starting execution of a group of commands
    running_list = []
    finished_list = []
    while portion or running_list: # While not finished actions in portion
      # poll threads under execution
      for thread in running_list:
        if not thread.is_alive():
          finished_list.append(thread)
        # Remove finished from the running list
      running_list[:] = [b for b in running_list if not b in finished_list]
      # Start next actions
      free_slots = self.MAX_CONCURRENT_ACTIONS - len(running_list)
      while free_slots > 0 and portion: # Start new threads if available
        command = portion.pop()
        logger.debug("Took an element of Queue: " + pprint.pformat(command))
        if command['commandType'] == self.EXECUTION_COMMAND:
          # Start separate threads for commands of this type
          action_thread = Thread(target =  self.execute_command_safely, args = (command, ))
          running_list.append(action_thread)
          free_slots -= 1
          action_thread.start()
        elif command['commandType'] == self.STATUS_COMMAND:
          # Execute status commands immediately, in current thread
          self.execute_status_command(command)
        else:
          logger.error("Unrecognized command " + pprint.pformat(command))
    pass


  def execute_command_safely(self, command):
    # make sure we log failures
    try:
      self.execute_command(command)
    except Exception, err:
      # Should not happen
      traceback.print_exc()
      logger.warn(err)


  def execute_command(self, command):
    clusterName = command['clusterName']
    commandId = command['commandId']

    logger.info("Executing command with id = " + str(commandId) +\
                " for role = " + command['role'] + " of " +\
                "cluster " + clusterName)
    logger.debug(pprint.pformat(command))

    taskId = command['taskId']
    # Preparing 'IN_PROGRESS' report
    in_progress_status = self.commandStatuses.generate_report_template(command)
    in_progress_status.update({
      'tmpout': self.tmpdir + os.sep + 'output-' + str(taskId) + '.txt',
      'tmperr': self.tmpdir + os.sep + 'errors-' + str(taskId) + '.txt',
      'status': self.IN_PROGRESS_STATUS
    })
    self.commandStatuses.put_command_status(command, in_progress_status)
    # running command
    # Create a new instance of executor for the current thread
    puppetExecutor = PuppetExecutor.PuppetExecutor(
      self.config.get('puppet', 'puppetmodules'),
      self.config.get('puppet', 'puppet_home'),
      self.config.get('puppet', 'facter_home'),
      self.config.get('agent', 'prefix'), self.config)
    if command['roleCommand'] == ActionQueue.ROLE_COMMAND_UPGRADE:
      # Create new instances for the current thread
      pythonExecutor = PythonExecutor.PythonExecutor(
          self.config.get('agent', 'prefix'), self.config)
      upgradeExecutor = UpgradeExecutor.UpgradeExecutor(pythonExecutor,
          puppetExecutor, self.config)
      commandresult = upgradeExecutor.perform_stack_upgrade(command, in_progress_status['tmpout'],
        in_progress_status['tmperr'])
    else:
      commandresult = puppetExecutor.runCommand(command, in_progress_status['tmpout'],
        in_progress_status['tmperr'])
    # dumping results
    status = "COMPLETED"
    if commandresult['exitcode'] != 0:
      status = "FAILED"
    roleResult = self.commandStatuses.generate_report_template(command)
    # assume some puppet plumbing to run these commands
    roleResult.update({
      'stdout': commandresult['stdout'],
      'stderr': commandresult['stderr'],
      'exitCode': commandresult['exitcode'],
      'status': status,
    })
    if roleResult['stdout'] == '':
      roleResult['stdout'] = 'None'
    if roleResult['stderr'] == '':
      roleResult['stderr'] = 'None'

    # let ambari know that configuration tags were applied
    if status == 'COMPLETED':
      configHandler = ActualConfigHandler(self.config)
      if command.has_key('configurationTags'):
        configHandler.write_actual(command['configurationTags'])
        roleResult['configurationTags'] = command['configurationTags']

      if command.has_key('roleCommand') and command['roleCommand'] == 'START':
        configHandler.copy_to_component(command['role'])
        roleResult['configurationTags'] = configHandler.read_actual_component(command['role'])
    self.commandStatuses.put_command_status(command, roleResult)


  def execute_status_command(self, command):
    try:
      cluster = command['clusterName']
      service = command['serviceName']
      component = command['componentName']
      configurations = command['configurations']
      if configurations.has_key('global'):
        globalConfig = configurations['global']
      else:
        globalConfig = {}
      livestatus = LiveStatus(cluster, service, component,
                              globalConfig, self.config)
      result = livestatus.build()
      logger.debug("Got live status for component " + component + \
                   " of service " + str(service) + \
                   " of cluster " + str(cluster))
      logger.debug(pprint.pformat(result))
      if result is not None:
        self.commandStatuses.put_command_status(command, result)
    except Exception, err:
      traceback.print_exc()
      logger.warn(err)
    pass


  # Store action result to agent response queue
  def result(self):
    return self.commandStatuses.generate_report()


  def status_update_callback(self):
    """
    Actions that are executed every time when command status changes
    """
    self.controller.heartbeat_wait_event.set()
