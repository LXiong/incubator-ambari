/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

var App = require('app');
require('controllers/main/admin/highAvailability/progress_controller');

App.HighAvailabilityRollbackController = App.HighAvailabilityProgressPageController.extend({

  name: "highAvailabilityRollbackController",

  failedTask: null,
  configsSaved: false,
  deletedHdfsClients: 0,
  numOfDelOperations: 0,
  isRollback: true,
  hostsToPerformDel: [],

  commands: [
    'stopAllServices',
    'restoreHBaseConfigs',
    'stopFailoverControllers',
    'deleteFailoverControllers',
    'stopStandbyNameNode',
    'stopNameNode',
    'restoreHDFSConfigs',
    'enableSecondaryNameNode',
    'stopJournalNodes',
    'deleteJournalNodes',
    'deleteAdditionalNameNode',
    'startAllServices'
  ],

  loadStep: function () {
    this.initData();
    this.clearStep();
    this.loadTasks();
    this.addObserver('tasks.@each.status', this, 'onTaskStatusChange');
    this.onTaskStatusChange();
  },

  initData: function () {
    this.loadMasterComponentHosts();
    this.loadFailedTask();
    this.loadHdfsClientHosts();
  },

  setCommandsAndTasks: function(tmpTasks) {
    var fTask = this.get('failedTask');
    var newCommands = [];
    var newTasks = [];
    var index = [
      'deleteSNameNode',
      'startAllServices',
      'reconfigureHBase',
      'startZKFC',
      'installZKFC',
      'startSecondNameNode',
      'startNameNode',
      'startZooKeeperServers',
      'reconfigureHDFS',
      'disableSNameNode',
      'startJournalNodes',
      'installJournalNodes',
      'installNameNode',
      'stopAllServices'
    ].indexOf(fTask.command);

    if(index > 6){
      --index;
    }
    newCommands = this.get('commands').splice(index);
    this.set('commands', newCommands);
    newTasks = tmpTasks.splice(index);
    for (var i = 0; i < newTasks.length; i++) {
      newTasks[i].id = i;
    };
    this.set('tasks', newTasks);
    var hbaseTask = this.get('tasks').findProperty('command', 'restoreHBaseConfigs');
    if (!App.Service.find().someProperty('serviceName', 'HBASE') && hbaseTask) {
      this.get('tasks').splice(hbaseTask.get('id'), 1);
    }
  },

  clearStep: function () {
    this.set('isSubmitDisabled', true);
    this.set('tasks', []);
    this.set('logs', []);
    this.set('currentRequestIds', []);
    var commands = this.get('commands');
    var tmpTasks = [];
    for (var i = 0; i < commands.length; i++) {
      tmpTasks.pushObject(Ember.Object.create({
        title: Em.I18n.t('admin.highAvailability.rollback.task' + i + '.title'),
        status: 'PENDING',
        id: i,
        command: commands[i],
        showRetry: false,
        showRollback: false,
        showSkip: false,
        name: Em.I18n.t('admin.highAvailability.rollback.task' + i + '.title'),
        displayName: Em.I18n.t('admin.highAvailability.rollback.task' + i + '.title'),
        progress: 0,
        isRunning: false,
        hosts: []
      }));
    }
    this.setCommandsAndTasks(tmpTasks);
  },

  onTaskStatusChange: function () {
    if (!this.get('tasks').someProperty('status', 'IN_PROGRESS') && !this.get('tasks').someProperty('status', 'QUEUED') && !this.get('tasks').someProperty('status', 'FAILED')) {
      var nextTask = this.get('tasks').findProperty('status', 'PENDING');
      if (nextTask) {
        this.set('status', 'IN_PROGRESS');
        this.runTask(nextTask.get('id'));
        this.setTaskStatus(nextTask.get('id'), 'QUEUED');
        this.set('currentTaskId', nextTask.get('id'));
      } else {
        this.set('status', 'COMPLETED');
        this.set('isSubmitDisabled', false);
      }
    } else if (this.get('tasks').someProperty('status', 'FAILED')) {
      this.set('status', 'FAILED');
      this.get('tasks').findProperty('status', 'FAILED').set('showRetry', true);
      this.get('tasks').findProperty('status', 'FAILED').set('showSkip', true);
    }

    var statuses = this.get('tasks').mapProperty('status');
    var logs = this.get('tasks').mapProperty('hosts');
    var requestIds = this.get('currentRequestIds');
    this.saveTasksStatuses(statuses);
    this.saveRequestIds(requestIds);
    this.saveLogs(logs);
    App.clusterStatus.setClusterStatus({
      clusterName: this.get('content.cluster.name'),
      clusterState: 'HIGH_AVAILABILITY_ROLLBACK',
      wizardControllerName: 'highAvailabilityRollbackController',
      localdb: App.db.data
    });
  },

  skipTask: function () {
    var task = this.get('tasks').findProperty('status', 'FAILED');
    task.set('showRetry', false);
    task.set('showSkip', false);
    task.set('status', 'COMPLETED');
  },

  retryTask: function () {
    var task = this.get('tasks').findProperty('status', 'FAILED');
    task.set('showRetry', false);
    task.set('showSkip', false);
    task.set('status', 'PENDING');
  },

  onTaskCompleted: function () {
    var curTaskStatus = this.getTaskStatus(this.get('currentTaskId'));
    if (curTaskStatus != 'FAILED' && curTaskStatus != 'TIMEDOUT' && curTaskStatus != 'ABORTED') {
      this.setTaskStatus(this.get('currentTaskId'), 'COMPLETED');
    }
  },

  getTaskStatus: function (taskId) {
    return this.get('tasks').findProperty('id', taskId).get('status');
  },

  loadFailedTask: function(){
    var failedTask = App.db.getHighAvailabilityWizardFailedTask();
    this.set('failedTask', failedTask);
  },

  done: function () {
    if (!this.get('isSubmitDisabled')) {
      this.removeObserver('tasks.@each.status', this, 'onTaskStatusChange');
      this.popup.proceedOnClose();
    }
  },

  stopAllServices: function(){
    App.ajax.send({
      name: 'admin.high_availability.stop_all_services',
      sender: this,
      success: 'startPolling',
      error: 'onTaskError'
    });
  },
  restoreHBaseConfigs: function(){
    this.loadConfigTag("hbaseSiteTag");
    var hbaseSiteTag = this.get("content.hbaseSiteTag");
    App.ajax.send({
      name: 'admin.high_availability.load_hbase_configs',
      sender: this,
      data: {
        hbaseSiteTag: hbaseSiteTag
      },
      success: 'onLoadHbaseConfigs',
      error: 'onTaskError'
    });
  },

  stopFailoverControllers: function(){
    var hostNames = this.get('content.masterComponentHosts').filterProperty('component', 'NAMENODE').mapProperty('hostName');
    this.stopComponent('ZKFC', hostNames);
  },
  deleteFailoverControllers: function(){
    var hostNames = this.get('content.masterComponentHosts').filterProperty('component', 'NAMENODE').mapProperty('hostName');
    this.checkBeforeDelete('ZKFC', hostNames);
  },
  stopStandbyNameNode: function(){
    var hostName = this.get('content.masterComponentHosts').findProperty('isAddNameNode', true).hostName;;
    this.stopComponent('NAMENODE', hostName);
  },
  stopNameNode: function(){
    var hostNames = this.get('content.masterComponentHosts').findProperty('isCurNameNode').hostName;
    this.stopComponent('NAMENODE', hostNames);
  },
  restoreHDFSConfigs: function(){
    this.unInstallHDFSClients();
  },
  enableSecondaryNameNode: function(){
    var hostName = this.get('content.masterComponentHosts').findProperty('component', 'SECONDARY_NAMENODE').hostName;
    this.installComponent('SECONDARY_NAMENODE', hostName, hostName.length);
  },
  stopJournalNodes: function(){
    var hostNames = this.get('content.masterComponentHosts').filterProperty('component', 'JOURNALNODE').mapProperty('hostName');
    this.stopComponent('JOURNALNODE', hostNames);
  },
  deleteJournalNodes: function(){
    var hostNames = this.get('content.masterComponentHosts').filterProperty('component', 'JOURNALNODE').mapProperty('hostName');
    this.unInstallComponent('JOURNALNODE', hostNames);
  },
  deleteAdditionalNameNode: function(){
    var hostNames = this.get('content.masterComponentHosts').filterProperty('isAddNameNode', true).mapProperty('hostName');
    this.unInstallComponent('NAMENODE', hostNames);
  },
  startAllServices: function(){
    App.ajax.send({
      name: 'admin.high_availability.start_all_services',
      sender: this,
      success: 'startPolling',
      error: 'onTaskError'
    });
  },

  onLoadHbaseConfigs: function (data) {
    var hbaseSiteProperties = data.items.findProperty('type', 'hbase-site').properties;
    App.ajax.send({
      name: 'admin.high_availability.save_configs',
      sender: this,
      data: {
        siteName: 'hbase-site',
        properties: hbaseSiteProperties
      },
      success: 'onTaskCompleted',
      error: 'onTaskError'
    });
  },

  stopComponent: function (componentName, hostName) {
    if (!(hostName instanceof Array)) {
      hostName = [hostName];
    }
    for (var i = 0; i < hostName.length; i++) {
      App.ajax.send({
        name: 'admin.high_availability.stop_component',
        sender: this,
        data: {
          hostName: hostName[i],
          componentName: componentName,
          displayName: App.format.role(componentName),
          taskNum: hostName.length
        },
        success: 'startPolling',
        error: 'onTaskError'
      });
    }
  },

  onDeletedHDFSClient: function () {
    var deletedHdfsClients = this.get('deletedHdfsClients');
    var hostName = this.get("content.hdfsClientHostNames");
    var notDeletedHdfsClients = hostName.length - deletedHdfsClients;
    if (notDeletedHdfsClients > 1 && hostName.length != 1 ) {
      this.set('deletedHdfsClients', deletedHdfsClients+1);
      return;
    }
    this.loadConfigTag("hdfsSiteTag");
    this.loadConfigTag("coreSiteTag");
    var hdfsSiteTag = this.get("content.hdfsSiteTag");
    var coreSiteTag = this.get("content.coreSiteTag");
    App.ajax.send({
      name: 'admin.high_availability.load_configs',
      sender: this,
      data: {
        hdfsSiteTag: hdfsSiteTag,
        coreSiteTag: coreSiteTag
      },
      success: 'onLoadConfigs',
      error: 'onTaskError'
    });
  },

  onLoadConfigs: function (data) {
    this.set('configsSaved', false);
    App.ajax.send({
      name: 'admin.high_availability.save_configs',
      sender: this,
      data: {
        siteName: 'hdfs-site',
        properties: data.items.findProperty('type', 'hdfs-site').properties
      },
      success: 'onHdfsConfigsSaved',
      error: 'onTaskError'
    });
    App.ajax.send({
      name: 'admin.high_availability.save_configs',
      sender: this,
      data: {
        siteName: 'core-site',
        properties: data.items.findProperty('type', 'core-site').properties
      },
      success: 'onHdfsConfigsSaved',
      error: 'onTaskError'
    });
  },

  onHdfsConfigsSaved: function () {
    if (!this.get('configsSaved')) {
      this.set('configsSaved', true);
      return;
    }
    this.onTaskCompleted();
  },

  unInstallHDFSClients: function () {
    var hostName = this.get("content.hdfsClientHostNames");
    for (var i = 0; i < hostName.length; i++) {
      App.ajax.send({
        name: 'admin.high_availability.delete_component',
        sender: this,
        data: {
          componentName: 'HDFS_CLIENT',
          hostName: hostName[i]
        },
        success: 'onDeletedHDFSClient',
        error: 'onTaskError'
      });
    }
  },

  unInstallComponent: function (componentName, hostName) {
    if (!(hostName instanceof Array)) {
      hostName = [hostName];
    }
    for (var i = 0; i < hostName.length; i++) {
      App.ajax.send({
        name: 'admin.high_availability.maintenance_mode',
        sender: this,
        data: {
          hostName: hostName[i],
          componentName: componentName,
          taskNum: hostName.length,
          callback: 'checkBeforeDelete'
        },
        success: 'checkResult',
        error: 'checkResult'
      });
    }
  },

  checkBeforeDelete: function (componentName, hostName){
    this.set('hostsToPerformDel', []);
    if (!(hostName instanceof Array)) {
      hostName = [hostName];
    }
    for (var i = 0; i < hostName.length; i++) {
      App.ajax.send({
        name: 'admin.high_availability.getHostComponent',
        sender: this,
        data: {
          componentName: componentName,
          hostName: hostName[i],
          taskNum: hostName.length,
          callback: 'deleteComponent'
        },
        success: 'checkResult',
        error: 'checkResult'
      });
    }
  },

  checkResult: function () {
    var callback = arguments[2].callback;
    var hostName = arguments[2].hostName;
    var componentName = arguments[2].componentName;
    var taskNum = arguments[2].taskNum;
    var hostsToPerformDel = this.get('hostsToPerformDel');
    if(arguments[1] != 'error'){
      hostsToPerformDel.push({
        hostName: hostName,
        isOnHost: true
      });
    }else{
      hostsToPerformDel.push({
        hostName: 'error',
        isOnHost: false
      });
    }
    if(hostsToPerformDel.length == taskNum){
      var hostsForDel = hostsToPerformDel.filterProperty('isOnHost', true).mapProperty('hostName');
      this.set('hostsToPerformDel', []);
      if(hostsForDel.length == 0){
        this.onTaskCompleted();
        return;
      }
      this[callback](componentName, hostsForDel);
    }
  },

  deleteComponent: function (componentName, hostName) {
    if (!(hostName instanceof Array)) {
      hostName = [hostName];
    }
    this.set('numOfDelOperations', hostName.length);
    for (var i = 0; i < hostName.length; i++) {
      App.ajax.send({
        name: 'admin.high_availability.delete_component',
        sender: this,
        data: {
          componentName: componentName,
          hostName: hostName[i]
        },
        success: 'onDeleteComplete',
        error: 'onTaskError'
      });
    }
  },

  onDeleteComplete: function () {
    var leftOp = this.get('numOfDelOperations');
    if(leftOp > 1){
      this.set('numOfDelOperations', leftOp-1);
      return;
    }
    this.onTaskCompleted();
  }

});
