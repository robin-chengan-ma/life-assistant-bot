import "leaflet/dist/leaflet.css";

import type { Map as LeafletMap } from "leaflet";
import type { CSSProperties } from "react";
import { useEffect, useRef } from "react";
import { StyleSheet, View } from "react-native";

export type ExplorationMapMarker = {
  id: string;
  latitude: number;
  longitude: number;
  title: string;
  type: string;
};

type ExplorationMapProps = {
  markers: ExplorationMapMarker[];
};

const DEFAULT_CENTER: [number, number] = [23.6978, 120.9605];

export function ExplorationMap({ markers }: ExplorationMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);

  useEffect(() => {
    let cancelled = false;

    const initializeMap = async () => {
      if (!containerRef.current || mapRef.current) return;
      const leaflet = await import("leaflet");
      if (cancelled || !containerRef.current) return;

      const map = leaflet.map(containerRef.current, {
        attributionControl: true,
        center: DEFAULT_CENTER,
        scrollWheelZoom: true,
        zoom: 7,
      });
      leaflet.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      }).addTo(map);

      const bounds = leaflet.latLngBounds([]);
      markers.forEach((marker) => {
        const position = leaflet.latLng(marker.latitude, marker.longitude);
        leaflet.circleMarker(position, {
          color: "#0E5E55",
          fillColor: "#54C8B7",
          fillOpacity: 0.92,
          radius: 9,
          weight: 3,
        }).bindPopup(`<strong>${marker.title}</strong><br />${marker.type}`).addTo(map);
        bounds.extend(position);
      });
      if (markers.length > 0) map.fitBounds(bounds, { maxZoom: 13, padding: [36, 36] });
      mapRef.current = map;
    };

    void initializeMap();
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [markers]);

  return (
    <View style={styles.frame}>
      <div aria-label="探索地圖技術驗證" ref={containerRef} style={styles.map as CSSProperties} />
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    borderColor: "#D8E2DF",
    borderRadius: 18,
    borderWidth: 1,
    height: 520,
    overflow: "hidden",
    width: "100%",
  },
  map: {
    height: "100%",
    width: "100%",
  },
});
