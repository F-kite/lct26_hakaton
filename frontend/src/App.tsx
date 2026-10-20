import { Route, Routes } from "react-router-dom";

import NotFoundPage from "./pages/NotFoundPage";
import ResultsPage from "./pages/ResultsPage";
import SearchHomePage from "./pages/SearchHomePage";
import SignalDetailPage from "./pages/SignalDetailPage";
import SignalSourcesPage from "./pages/SignalSourcesPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<SearchHomePage />} />
      <Route path="/results/:queryId" element={<ResultsPage />} />
      <Route path="/results/:queryId/signals/:signalId" element={<SignalDetailPage />} />
      <Route path="/results/:queryId/signals/:signalId/sources" element={<SignalSourcesPage />} />
      <Route path="/results/:queryId/signals/:signalId/analysts" element={<SignalSourcesPage kind="analysts" />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
