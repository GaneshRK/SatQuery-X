"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import AppShell from "../../components/AppShell";
import SectionTitle from "../../components/SectionTitle";
import { analysisApi } from "../../services/contractClient";
import { FolderPlus } from "lucide-react";

const initialCards = [
  [
    "Coimbatore Vegetation Analysis",
    "Updated Sep 2026",
    "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=500&q=80",
  ],
  [
    "Flood Impact Assessment - Kerala",
    "Updated Aug 2026",
    "https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=500&q=80",
  ],
  [
    "Urban Expansion - Chennai",
    "Updated Aug 2026",
    "https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=500&q=80",
  ],
  [
    "Water Body Detection - Tamil Nadu",
    "Updated Jul 2026",
    "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=500&q=80",
  ],
];

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");

  useEffect(() => {
    analysisApi
      .projects()
      .then(({ data }) => {
        if (data && data.length > 0) {
          setProjects(data);
        }
      })
      .catch((e) => console.warn("Projects load:", e));
  }, []);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    try {
      const { data } = await analysisApi.createProject({
        name: newProjectName.trim(),
        description: newProjectDesc.trim(),
      });
      setProjects((prev) => [data, ...prev]);
      setNewProjectName("");
      setNewProjectDesc("");
      setShowModal(false);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <AppShell>
      <div className="page">
        <SectionTitle
          title="My Projects"
          subtitle="Create and manage your geospatial analysis investigations."
          action={
            <button className="btn primary" onClick={() => setShowModal(true)}>
              + New Project
            </button>
          }
        />

        {showModal && (
          <div
            className="panel"
            style={{
              maxWidth: 500,
              marginBottom: 16,
              background: "#081e2a",
              border: "1px solid #2ee79b",
            }}
          >
            <h3 style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <FolderPlus size={16} color="#2ee79b" /> Create New Analysis Project
            </h3>
            <form onSubmit={handleCreateProject} style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
              <input
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                placeholder="Project title (e.g. Western Ghats Forest Cover)"
                required
                style={{
                  background: "#071620",
                  border: "1px solid #1c3d4c",
                  padding: "8px 12px",
                  borderRadius: 6,
                  color: "#fff",
                }}
              />
              <textarea
                value={newProjectDesc}
                onChange={(e) => setNewProjectDesc(e.target.value)}
                placeholder="Project description & goals..."
                rows={2}
                style={{
                  background: "#071620",
                  border: "1px solid #1c3d4c",
                  padding: "8px 12px",
                  borderRadius: 6,
                  color: "#fff",
                }}
              />
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn ghost small"
                  onClick={() => setShowModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn primary small">
                  Save Project
                </button>
              </div>
            </form>
          </div>
        )}

        <div className="projects-grid">
          {projects.map((p) => (
            <Link href="/analysis" className="project-card" key={p.id}>
              <img
                src="https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=500&q=80"
                alt="Project Thumbnail"
              />
              <div>
                <h3>{p.name}</h3>
                <span>{p.description || "Created recently"}</span>
              </div>
              <b>⋮</b>
            </Link>
          ))}

          {initialCards.map(([title, date, img]) => (
            <Link href="/analysis" className="project-card" key={title}>
              <img src={img} alt={title} />
              <div>
                <h3>{title}</h3>
                <span>{date}</span>
              </div>
              <b>⋮</b>
            </Link>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
