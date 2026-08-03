"use client";

import { Environment, Float, MeshDistortMaterial, Sphere } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Suspense, useMemo } from "react";
import * as THREE from "three";

import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

/**
 * AIVisualization — a small "neural network" scene for the Hero section:
 * a purple core sphere with orbiting nodes connected by lines, evoking
 * an AI/ML decision graph without being a literal (and slower) particle
 * system. Self-contained Canvas (distinct from AnimatedBackground's
 * full-page fixed one) so it can be sized/positioned inline within the
 * Hero's layout rather than behind the whole page.
 */
const NODE_COUNT = 8;

function useOrbitPositions(count: number, radius: number): [number, number, number][] {
  return useMemo(() => {
    const positions: [number, number, number][] = [];
    for (let i = 0; i < count; i++) {
      const theta = (i / count) * Math.PI * 2;
      const phi = Math.acos(2 * ((i + 0.5) / count) - 1);
      positions.push([
        radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.sin(phi) * Math.sin(theta),
        radius * Math.cos(phi),
      ]);
    }
    return positions;
  }, [count, radius]);
}

function ConnectionLines({ nodePositions }: { nodePositions: [number, number, number][] }) {
  const geometry = useMemo(() => {
    const points: THREE.Vector3[] = [];
    for (const pos of nodePositions) {
      points.push(new THREE.Vector3(0, 0, 0), new THREE.Vector3(...pos));
    }
    return new THREE.BufferGeometry().setFromPoints(points);
  }, [nodePositions]);

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#8b5fff" transparent opacity={0.25} />
    </lineSegments>
  );
}

function CoreSphere({ reduceMotion }: { reduceMotion: boolean }) {
  return (
    <Sphere args={[0.9, 64, 64]}>
      <MeshDistortMaterial
        color="#6c3bff"
        distort={reduceMotion ? 0 : 0.4}
        speed={reduceMotion ? 0 : 2}
        roughness={0.1}
        metalness={0.3}
      />
    </Sphere>
  );
}

function OrbitNode({
  position,
  reduceMotion,
}: {
  position: [number, number, number];
  reduceMotion: boolean;
}) {
  const node = (
    <Sphere args={[0.14, 32, 32]} position={position}>
      <meshStandardMaterial color="#a78bfa" emissive="#8b5fff" emissiveIntensity={0.6} />
    </Sphere>
  );

  // Same explicit prefers-reduced-motion check as AnimatedBackground —
  // render the node statically (no orbiting Float animation) instead.
  if (reduceMotion) {
    return node;
  }

  return (
    <Float speed={2} rotationIntensity={0.6} floatIntensity={2}>
      {node}
    </Float>
  );
}

function Scene({ reduceMotion }: { reduceMotion: boolean }) {
  const nodePositions = useOrbitPositions(NODE_COUNT, 2.3);
  return (
    <>
      <ambientLight intensity={0.7} />
      <pointLight position={[3, 3, 3]} intensity={50} color="#8b5fff" />
      <pointLight position={[-3, -2, 2]} intensity={30} color="#ffffff" />
      <CoreSphere reduceMotion={reduceMotion} />
      <ConnectionLines nodePositions={nodePositions} />
      {nodePositions.map((pos, i) => (
        <OrbitNode key={i} position={pos} reduceMotion={reduceMotion} />
      ))}
    </>
  );
}

export function AIVisualization() {
  const prefersReducedMotion = usePrefersReducedMotion();

  return (
    <div className="h-full w-full" aria-hidden="true">
      <Canvas
        dpr={[1, 1.5]}
        camera={{ position: [0, 0, 6], fov: 50 }}
        gl={{ antialias: true, alpha: true }}
      >
        <Suspense fallback={null}>
          <Scene reduceMotion={prefersReducedMotion} />
          {/* Self-hosted HDRI — see AnimatedBackground.tsx's identical comment
          for the full rationale (drei's `preset` prop is CDN-dependent and
          explicitly not recommended for production by drei's own docs). */}
      <Environment files="/assets/hdri/potsdamer_platz_1k.hdr" environmentIntensity={0.25} />
        </Suspense>
      </Canvas>
    </div>
  );
}
