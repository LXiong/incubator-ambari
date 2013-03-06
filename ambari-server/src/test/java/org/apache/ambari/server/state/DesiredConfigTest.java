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
package org.apache.ambari.server.state;

import java.util.Arrays;
import java.util.List;

import org.junit.Assert;
import org.junit.Test;

/**
 * Tests desired config instances.
 */
public class DesiredConfigTest {

  @Test
  public void testDesiredConfig() throws Exception {
    DesiredConfig dc = new DesiredConfig();
    dc.setServiceName("service");
    dc.setVersion("global");
    
    Assert.assertEquals("Expected service 'service'", "service", dc.getServiceName());
    Assert.assertEquals("Expected version 'global'", "global", dc.getVersion());
    Assert.assertNull("Expected null host overrides", dc.getHostOverrides());
    
    List<String> hosts = Arrays.asList("h1", "h2", "h3");
    dc.setHostOverrides(hosts);
    
    Assert.assertNotNull("Expected host overrides to be set", dc.getHostOverrides());
    Assert.assertEquals("Expected host override equality", hosts, dc.getHostOverrides());
  }
  
}