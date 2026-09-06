import type { Metadata } from 'next';
import './globals.css';
import 'maplibre-gl/dist/maplibre-gl.css';
import Providers from '../components/Providers';

export const metadata: Metadata = {
  title: 'SatQuery AI — Agentic Geospatial Intelligence Engine',
  description: 'Multimodal Satellite Reasoning Engine for RS-VQA, Cross-Modal Fusion, and Bi-Temporal Change Intelligence (SIH26167).',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="dark">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
