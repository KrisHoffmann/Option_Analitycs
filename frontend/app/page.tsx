import PayoffVisualizer from "@/components/PayoffVisualizer";

// Server component: the interactive visualizer is the client leaf. The shared
// header/nav lives in the root layout.
export default function Home() {
  return <PayoffVisualizer />;
}
