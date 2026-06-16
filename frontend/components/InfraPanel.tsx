"use client";

import { Incident, Server } from "@/lib/types";
import ServerTile from "./ServerTile";

interface Props {
  servers: Server[];
  incident: Incident | null;
}

export default function InfraPanel({ servers, incident }: Props) {
  // blast radius = depended_on_by of the targeted server
  const blastRadiusIds = new Set<string>();
  if (incident) {
    const targetServer = servers.find((s) => s.id === incident.target);
    if (targetServer) {
      targetServer.depended_on_by.forEach((id) => blastRadiusIds.add(id));
    }
  }

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
