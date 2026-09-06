"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FolderKanban,
  FolderPlus,
  Search,
  Bot,
  Calendar,
  Layers,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Filter,
} from "lucide-react";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Modal } from "../../components/ui/Modal";
import { analysisApi } from "../../services/contractClient";

interface ProjectItem {
  id: string | number;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
  imagery_count?: number;
  analysis_count?: number;
  status?: string;
}

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchProjects = async () => {
    try {
      setLoading(true);
      const { data } = await analysisApi.projects();
      const items = Array.isArray(data) ? data : data.results || [];
      setProjects(items);
    } catch (err) {
      console.warn("Error fetching projects:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim() || isSubmitting) return;

    try {
      setIsSubmitting(true);
      await analysisApi.createProject({
        name: newProjectName.trim(),
        description: newProjectDesc.trim(),
      });
      setNewProjectName("");
      setNewProjectDesc("");
      setShowCreateModal(false);
      await fetchProjects();
    } catch (err) {
      console.error("Failed to create project:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredProjects = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (p.description && p.description.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <AppShell>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <SectionTitle
          title="Mission Workspaces & Projects"
          subtitle="Organize multi-temporal planetary investigations, sensor catalogs, and verified evidence logs."
          action={
            <Button
              variant="primary"
              icon={<FolderPlus className="w-4 h-4" />}
              onClick={() => setShowCreateModal(true)}
            >
              New Investigation
            </Button>
          }
        />

        {/* Search & Filter Header */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="relative w-full sm:w-80">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Search workspaces by name or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div className="text-xs font-mono text-slate-400">
            <span>Total Investigations: </span>
            <span className="text-cyan-400 font-bold">{projects.length}</span>
          </div>
        </div>

        {/* Projects Grid or Real Empty State */}
        {loading ? (
          <div className="py-24 text-center text-xs text-slate-500">
            Loading investigation workspaces...
          </div>
        ) : filteredProjects.length === 0 ? (
          <Card className="p-12 text-center space-y-4 max-w-xl mx-auto">
            <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center mx-auto">
              <FolderKanban className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-slate-100">
                {searchQuery ? "No Matching Workspaces" : "No Investigation Projects Yet"}
              </h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                {searchQuery
                  ? "Try refining your search keyword."
                  : "Create an investigation workspace to group multi-temporal satellite analyses, Copernicus rasters, and SIH proof chains."}
              </p>
            </div>
            {!searchQuery && (
              <Button
                variant="primary"
                icon={<FolderPlus className="w-4 h-4" />}
                onClick={() => setShowCreateModal(true)}
              >
                Create First Investigation
              </Button>
            )}
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredProjects.map((project) => (
              <Card
                key={project.id}
                className="p-5 hover:border-cyan-500/40 transition-all flex flex-col justify-between space-y-4"
              >
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 flex items-center justify-center shrink-0">
                        <FolderKanban className="w-4 h-4" />
                      </div>
                      <h3 className="text-sm font-bold text-white leading-tight">
                        {project.name}
                      </h3>
                    </div>
                    <Badge variant="cyan" size="sm">
                      {project.status || "ACTIVE"}
                    </Badge>
                  </div>

                  <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                    {project.description || "Geospatial Earth observation investigation."}
                  </p>
                </div>

                <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                  <div className="flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5 text-slate-400" />
                    <span>
                      {project.created_at
                        ? new Date(project.created_at).toLocaleDateString()
                        : "Sep 2026"}
                    </span>
                  </div>

                  <button
                    onClick={() =>
                      router.push(`/assistant?q=${encodeURIComponent(`Analyze ${project.name}`)}`)
                    }
                    className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 font-sans font-semibold transition-colors"
                  >
                    <span>Open in AI Workstation</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </Card>
            ))}
          </div>
        )}

        {/* Modal: Create Investigation Project */}
        <Modal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          title="Create New Investigation Workspace"
          maxWidth="max-w-lg"
        >
          <form onSubmit={handleCreateProject} className="space-y-4 pt-2">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Investigation / Project Name
              </label>
              <input
                type="text"
                placeholder="e.g. Coimbatore Urban Expansion & Canopy Audit"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                required
                className="w-full px-3.5 py-2.5 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-sm focus:outline-none focus:border-cyan-400 transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Investigation Objective & Scope
              </label>
              <textarea
                placeholder="Describe the target AOI, monitoring interval, or physical hypotheses to test..."
                value={newProjectDesc}
                onChange={(e) => setNewProjectDesc(e.target.value)}
                rows={3}
                className="w-full px-3.5 py-2.5 rounded-lg bg-[#0d1f2e] border border-[#153245] text-white text-sm focus:outline-none focus:border-cyan-400 transition-colors"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button
                variant="ghost"
                type="button"
                onClick={() => setShowCreateModal(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                type="submit"
                loading={isSubmitting}
                icon={<FolderPlus className="w-4 h-4" />}
              >
                Create Workspace
              </Button>
            </div>
          </form>
        </Modal>
      </div>
    </AppShell>
  );
}
