"use client";

import { Environment, Float, MeshDistortMaterial, Sphere } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Suspense } from "react";

import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

/**
 * AnimatedBackground — the landing page's interactive 3D backdrop.
 * React Three Fiber + drei, per the "Elegant 3D visuals... React Three
 * Fiber, Three.js, Drei" requirement. Purely decorative/ambient (no
 * interaction required to use the site), `pointer-events-none` and
 * `fixed` behind everything so it never blocks content. Explicitly
 * checks `prefers-reduced-motion` via usePrefersReducedMotion() and
 * renders each orb statically (no Float wrapper, no material distortion
 * animation) when set, rather than relying on being low-amplitude alone.
 *
 * Kept as a single small scene (3 floating distorted spheres in the
 * white+purple palette) rather than a dense particle field — Document 2's
 * "Apple-level minimalism" direction argues for restraint even in the 3D
 * layer, and a light scene is also what keeps this hitting 60fps on
 * mid-range hardware without any manual perf tuning.
 */
function FloatingOrb({
  position,
  color,
  scale,
  speed,
  reduceMotion,
}: {
  position: [number, number, number];
  color: string;
  scale: number;
  speed: number;
  reduceMotion: boolean;
}) {
  const sphere = (
    <Sphere args={[1, 64, 64]} position={position} scale={scale}>
      <MeshDistortMaterial
        color={color}
        distort={reduceMotion ? 0 : 0.35}
        speed={reduceMotion ? 0 : 1.5}
        roughness={0.15}
        metalness={0.1}
        transparent
        opacity={0.55}
      />
    </Sphere>
  );

  // prefers-reduced-motion: reduce -> render the orb statically (no
  // Float wrapper, no MeshDistortMaterial animation) rather than the
  // previous implicit claim that low amplitude alone was sufficient —
  // an explicit media-query check, not just a slow/gentle default.
  if (reduceMotion) {
    return sphere;
  }

  return (
    <Float speed={speed} rotationIntensity={0.4} floatIntensity={1.2}>
      {sphere}
    </Float>
  );
}

export function AnimatedBackground() {
  const prefersReducedMotion = usePrefersReducedMotion();

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 -z-10 h-screen w-screen"
    >
      <Canvas
        dpr={[1, 1.5]}
        camera={{ position: [0, 0, 8], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
      >
        <Suspense fallback={null}>
          <ambientLight intensity={0.6} />
          <pointLight position={[5, 5, 5]} intensity={40} color="#8b5fff" />
          <pointLight position={[-5, -3, -5]} intensity={30} color="#6c3bff" />

          <FloatingOrb
            position={[-3.2, 1.5, -2]}
            color="#8b5fff"
            scale={1.6}
            speed={1.1}
            reduceMotion={prefersReducedMotion}
          />
          <FloatingOrb
            position={[3.4, -1.2, -3]}
            color="#6c3bff"
            scale={2.1}
            speed={0.8}
            reduceMotion={prefersReducedMotion}
          />
          <FloatingOrb
            position={[0.5, 2.4, -4]}
            color="#a78bfa"
            scale={1.1}
            speed={1.4}
            reduceMotion={prefersReducedMotion}
          />

          {/* Self-hosted HDRI, not drei's `preset` shortcut — drei's own
              docs explicitly say "preset property is not meant to be used
              in production environments and may fail as it relies on
              CDNs" (it fetches from raw.githack.com/pmndrs/drei-assets at
              runtime, which this app's CSP correctly does not allowlist).
              Same asset content as preset="city" (Poly Haven's
              "Potsdamer Platz," CC0-licensed), vendored locally instead. */}
          <Environment files="/assets/hdri/potsdamer_platz_1k.hdr" environmentIntensity={0.3} />
        </Suspense>
      </Canvas>
    </div>
  );
}
