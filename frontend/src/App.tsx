import { useEffect, useRef } from "react";

// Placeholder only: draws an empty grid. No game logic lives in the frontend.
const GRID_SIZE = 32;
const TILE_PX = 16;

export default function App() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const size = GRID_SIZE * TILE_PX;
    ctx.fillStyle = "#cfe8c4";
    ctx.fillRect(0, 0, size, size);
    ctx.strokeStyle = "#8fb584";
    ctx.lineWidth = 1;
    for (let i = 0; i <= GRID_SIZE; i++) {
      const p = i * TILE_PX + 0.5;
      ctx.beginPath();
      ctx.moveTo(p, 0);
      ctx.lineTo(p, size);
      ctx.moveTo(0, p);
      ctx.lineTo(size, p);
      ctx.stroke();
    }
  }, []);

  return (
    <main>
      <h1>Living Island</h1>
      <canvas ref={canvasRef} width={GRID_SIZE * TILE_PX + 1} height={GRID_SIZE * TILE_PX + 1} />
    </main>
  );
}
