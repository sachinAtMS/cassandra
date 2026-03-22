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
import java.util.List;
import java.util.Map;

import io.airlift.airline.Command;
import io.airlift.airline.Option;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.service.snapshot.ExternalSnapshotManager;
import org.apache.cassandra.tools.NodeProbe;
import org.apache.cassandra.tools.NodeTool.NodeToolCmd;
import org.apache.cassandra.tools.nodetool.formatter.TableBuilder;

@Command(name = "listbackups", description = "Lists incremental backups stored in the external snapshot_directory")
public class ListBackups extends NodeToolCmd
{
    @Option(title = "keyspace",
            name = { "-k", "--keyspace" },
            description = "Filter by keyspace name")
    private String keyspace = null;

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

        ExternalSnapshotManager manager = ExternalSnapshotManager.instance();
        Map<String, Map<String, List<String>>> backups = manager.listIncrementalBackups();

        if (backups.isEmpty())
        {
            out.println("No incremental backups found in external storage.");
            return;
        }

        out.println("Incremental Backups in External Storage:");
        out.println("Directory: " + org.apache.cassandra.config.DatabaseDescriptor.getSnapshotDirectory());
        out.println();

        TableBuilder table = new TableBuilder();
        table.add("Keyspace", "Table", "SSTable Files");

        int totalFiles = 0;
        for (Map.Entry<String, Map<String, List<String>>> ksEntry : backups.entrySet())
        {
            String ks = ksEntry.getKey();
            if (keyspace != null && !keyspace.equals(ks))
                continue;

            for (Map.Entry<String, List<String>> tblEntry : ksEntry.getValue().entrySet())
            {
                String tbl = tblEntry.getKey();
                List<String> files = tblEntry.getValue();
                table.add(ks, tbl, String.valueOf(files.size()));
                totalFiles += files.size();
            }
        }

        table.printTo(out);
        out.println();
        out.println("Total backup SSTable files: " + totalFiles);
    }
}
