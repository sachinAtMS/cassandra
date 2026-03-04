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

"""
Microsoft Entra ID Authentication Plugin for Apache Cassandra.

Provides an AuthProvider for the DataStax Python Cassandra driver that acquires
JWT tokens from Microsoft Entra ID and authenticates to Cassandra via SASL PLAIN.

Quick Start::

    from cassandra_entra_id_auth import EntraIdAuthProvider
    from cassandra.cluster import Cluster

    auth_provider = EntraIdAuthProvider(
        tenant_id='your-tenant-id',
        client_id='your-client-id',
        client_secret='your-client-secret'
    )
    cluster = Cluster(['cassandra-host'], auth_provider=auth_provider)
    session = cluster.connect()
"""

from cassandra_entra_id_auth.provider import (
    EntraIdAuthProvider,
    EntraIdAuthenticator,
)

__version__ = "1.0.0"
__all__ = ["EntraIdAuthProvider", "EntraIdAuthenticator"]
