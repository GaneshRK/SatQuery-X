import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'SatQuery-X — Agentic Geospatial Intelligence Engine',
  description: 'Multimodal Satellite Reasoning Engine for RS-VQA, Cross-Modal Fusion, and Bi-Temporal Change Intelligence (SIH26167).',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#070b13] flex flex-col font-sans">
        {children}
      </body>
    </html>
  );
}
