/*
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
package org.apache.cassandra.tools.nodetool;

import java.io.PrintStream;

import io.airlift.airline.Command;
import io.airlift.airline.Option;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.service.snapshot.ExternalSnapshotManager;
import org.apache.cassandra.tools.NodeProbe;
import org.apache.cassandra.tools.NodeTool.NodeToolCmd;

@Command(name = "clearbackups", description = "Clears incremental backup SSTables from the external snapshot_directory")
public class ClearBackups extends NodeToolCmd
{
    @Option(title = "keyspace",
            name = { "-k", "--keyspace" },
            description = "Filter by keyspace name")
    private String keyspace = null;

    @Option(title = "table",
            name = { "-t", "--table" },
            description = "Filter by table name (requires --keyspace)")
    private String table = null;

    @Override
    public void execute(NodeProbe probe)
    {
        PrintStream out = probe.output().out;

        // Ensure config is loaded (nodetool runs in a separate JVM)
        DatabaseDescriptor.toolInitialization(false);

        if (!ExternalSnapshotManager.isEnabled())
        {
            out.println("External snapshot storage is not enabled.");
            out.println("Requires: snapshot_directory set and uuid_sstable_identifiers_enabled=true");
            return;
        }

        if (table != null && keyspace == null)
        {
            out.println("ERROR: --table requires --keyspace");
            return;
        }

        ExternalSnapshotManager manager = ExternalSnapshotManager.instance();

        try
        {
            long deleted = manager.clearIncrementalBackups(keyspace, table);
            out.println("Cleared " + deleted + " incremental backup file(s) from external storage.");
        }
        catch (Exception e)
        {
            out.println("Error clearing incremental backups: " + e.getMessage());
        }
    }
}
