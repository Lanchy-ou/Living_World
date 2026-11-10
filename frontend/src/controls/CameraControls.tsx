import { Icon } from "./icons.tsx";

interface Props {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
}

/** Map zoom buttons. They only change the camera; the map component supplies the actions. */
export function CameraControls({ onZoomIn, onZoomOut, onFit }: Props) {
  return (
    <section className="map-controls" aria-label="Camera">
      <button type="button" className="icon-button" aria-label="Zoom out" title="Zoom out" onClick={onZoomOut}>
        <Icon name="minus" />
      </button>
      <button type="button" className="icon-button" aria-label="Zoom in" title="Zoom in" onClick={onZoomIn}>
        <Icon name="plus" />
      </button>
      <button type="button" className="text-button" title="Show the whole map" onClick={onFit}>
        <Icon name="fit" /> View entire island
      </button>
    </section>
  );
}
