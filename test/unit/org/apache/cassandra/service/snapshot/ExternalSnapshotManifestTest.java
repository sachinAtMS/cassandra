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

package org.apache.cassandra.service.snapshot;

import java.io.IOException;
import java.io.OutputStream;
import java.time.Instant;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

import org.apache.cassandra.config.DurationSpec;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileOutputStreamPlus;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIOException;

public class ExternalSnapshotManifestTest
{
    @Rule
    public TemporaryFolder tempFolder = new TemporaryFolder();

    @Test
    public void testSerializeAndDeserialize() throws IOException
    {
        File manifestFile = new File(tempFolder.newFile("test_manifest.json"));
        Instant now = Instant.parse("2025-01-15T10:30:00Z");
        Set<String> sstableIds = new HashSet<>(Arrays.asList("aabbccdd", "eeff0011"));

        ExternalSnapshotManifest original = new ExternalSnapshotManifest(
            Arrays.asList("na-1-big-Data.db", "na-1-big-Index.db"),
            sstableIds,
            null,  // no TTL
            now,
            Arrays.asList("-9223372036854775808", "0", "9223372036854775807"),
            "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "CREATE TABLE ks.tbl (id int PRIMARY KEY, name text);",
            "my_keyspace",
            "my_table",
            "host-uuid-1234"
        );

        original.serializeToJsonFile(manifestFile);

        ExternalSnapshotManifest deserialized = ExternalSnapshotManifest.deserializeFromJsonFile(manifestFile);

        assertThat(deserialized.getFiles()).containsExactly("na-1-big-Data.db", "na-1-big-Index.db");
        assertThat(deserialized.getSstableIds()).containsExactlyInAnyOrder("aabbccdd", "eeff0011");
        assertThat(deserialized.getCreatedAt()).isEqualTo(now);
        assertThat(deserialized.getExpiresAt()).isNull();
        assertThat(deserialized.getTokens()).containsExactly("-9223372036854775808", "0", "9223372036854775807");
        assertThat(deserialized.getSchemaVersion()).isEqualTo("a1b2c3d4-e5f6-7890-abcd-ef1234567890");
        assertThat(deserialized.getSchemaCql()).isEqualTo("CREATE TABLE ks.tbl (id int PRIMARY KEY, name text);");
        assertThat(deserialized.getKeyspace()).isEqualTo("my_keyspace");
        assertThat(deserialized.getTable()).isEqualTo("my_table");
        assertThat(deserialized.getHostId()).isEqualTo("host-uuid-1234");
    }

    @Test
    public void testSerializeWithTTL() throws IOException
    {
        File manifestFile = new File(tempFolder.newFile("test_ttl_manifest.json"));
        Instant now = Instant.parse("2025-01-15T10:30:00Z");
        DurationSpec.IntSecondsBound ttl = new DurationSpec.IntSecondsBound("3600s");

        ExternalSnapshotManifest original = new ExternalSnapshotManifest(
            Arrays.asList("file1.db"),
            new HashSet<>(Arrays.asList("id1")),
            ttl,
            now,
            Arrays.asList("100"),
            "v1", "CREATE TABLE ...", "ks", "tbl", "host1"
        );

        original.serializeToJsonFile(manifestFile);
        ExternalSnapshotManifest deserialized = ExternalSnapshotManifest.deserializeFromJsonFile(manifestFile);

        assertThat(deserialized.getExpiresAt()).isEqualTo(now.plusSeconds(3600));
    }

    @Test
    public void testIsExpired()
    {
        Instant now = Instant.parse("2025-01-15T10:30:00Z");
        DurationSpec.IntSecondsBound ttl = new DurationSpec.IntSecondsBound("60s");

        ExternalSnapshotManifest manifest = new ExternalSnapshotManifest(
            Arrays.asList("file1.db"), new HashSet<>(), ttl, now,
            null, null, null, "ks", "tbl", "host"
        );

        // Before expiry
        assertThat(manifest.isExpired(now.plusSeconds(30))).isFalse();
        // After expiry
        assertThat(manifest.isExpired(now.plusSeconds(61))).isTrue();
        // At exact expiry
        assertThat(manifest.isExpired(now.plusSeconds(60))).isFalse();
    }

    @Test
    public void testNoTTLNeverExpires()
    {
        Instant now = Instant.parse("2025-01-15T10:30:00Z");
        ExternalSnapshotManifest manifest = new ExternalSnapshotManifest(
            Arrays.asList("file1.db"), new HashSet<>(), null, now,
            null, null, null, "ks", "tbl", "host"
        );

        assertThat(manifest.isExpired(now.plusSeconds(9999999))).isFalse();
    }

    @Test
    public void testDeserializeFromInvalidFile() throws IOException
    {
        File invalidFile = new File(tempFolder.newFile("invalid"));
        assertThatIOException().isThrownBy(
            () -> ExternalSnapshotManifest.deserializeFromJsonFile(invalidFile));
    }

    @Test
    public void testDeserializeIgnoresUnknownFields() throws IOException
    {
        Map<String, Object> map = new HashMap<>();
        map.put("files", Arrays.asList("f1.db"));
        map.put("sstable_ids", Arrays.asList("id1"));
        map.put("keyspace", "ks");
        map.put("table", "tbl");
        map.put("future_field", "some_value"); // unknown field

        ObjectMapper mapper = new ObjectMapper();
        File manifestFile = new File(tempFolder.newFile("future_manifest.json"));
        mapper.writeValue((OutputStream) new FileOutputStreamPlus(manifestFile), map);

        ExternalSnapshotManifest manifest = ExternalSnapshotManifest.deserializeFromJsonFile(manifestFile);
        assertThat(manifest.getKeyspace()).isEqualTo("ks");
        assertThat(manifest.getTable()).isEqualTo("tbl");
        assertThat(manifest.getFiles()).containsExactly("f1.db");
    }

    @Test
    public void testEqualsAndHashCode()
    {
        Instant now = Instant.now();
        Set<String> ids = new HashSet<>(Arrays.asList("id1"));

        ExternalSnapshotManifest m1 = new ExternalSnapshotManifest(
            Arrays.asList("f1"), ids, null, now, null, "v1", null, "ks", "tbl", "host"
        );
        ExternalSnapshotManifest m2 = new ExternalSnapshotManifest(
            Arrays.asList("f1"), ids, null, now, null, "v1", null, "ks", "tbl", "host"
        );

        assertThat(m1).isEqualTo(m2);
        assertThat(m1.hashCode()).isEqualTo(m2.hashCode());
    }
}
