"use client";

import { Incident, Server } from "@/lib/types";
import ServerTile from "./ServerTile";

interface Props {
  servers: Server[];
  incident: Incident | null;
}

function deriveBlastRadius(servers: Server[], incident: Incident | null): Set<string> {
  const ids = new Set<string>();
  if (!incident?.diagnosis) return ids;

  // Use blast_radius from diagnosis if available
  const diagnosisRadius = incident.diagnosis.blast_radius ?? [];
  diagnosisRadius.forEach((id) => ids.add(id));

  // Also add depended_on_by of the affected service as fallback
  const affectedId = incident.diagnosis.affected_service;
  const affectedServer = servers.find((s) => s.id === affectedId);
  if (affectedServer) {
    affectedServer.depended_on_by.forEach((id) => ids.add(id));
  }

  return ids;
}

const INCIDENT_OPEN_STATUSES = new Set([
  "received",
  "diagnosing",
  "remediating",
  "verifying",
  "escalated",
  "awaiting_approval",
]);

export default function InfraPanel({ servers, incident }: Props) {
  const incidentOpen = incident ? INCIDENT_OPEN_STATUSES.has(incident.status) : false;
  const blastRadiusIds = incidentOpen ? deriveBlastRadius(servers, incident) : new Set<string>();

  return (
    <div className="flex flex-col h-full">
      {/* panel header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-700 shrink-0">
        <span className="w-2 h-2 rounded-full bg-blue-500" />
        <span className="text-xs font-mono text-zinc-400 tracking-widest uppercase">
          Infrastructure
        </span>
        {servers.length > 0 && (
          <span className="ml-auto text-[10px] text-zinc-600 font-mono">
            {servers.length} nodes
          </span>
        )}
      </div>

      {/* tiles */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {servers.length === 0 && (
          <p className="text-zinc-600 font-mono text-sm">
            Waiting for state…
          </p>
        )}
        {servers.map((server) => (
          <ServerTile
            key={server.id}
            server={server}
            isBlastRadius={blastRadiusIds.has(server.id)}
          />
        ))}
      </div>
    </div>
  );
}
