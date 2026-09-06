"use client";

import React, { Suspense } from "react";
import { AssistantWorkspaceContent } from "../components/assistant/AssistantWorkspaceContent";

export default function RootPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen bg-slate-950 text-cyan-400 font-mono text-xs">
          Initialising SatQuery AI Workstation...
        </div>
      }
    >
      <AssistantWorkspaceContent />
    </Suspense>
  );
}
