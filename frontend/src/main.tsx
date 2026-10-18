import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App.tsx";
import "./index.css";

const queryClient = new QueryClient();

const root = createRoot(document.getElementById("root")!);

// Витрина /dev — только в dev-сборке, вне BrowserRouter (внутри свои MemoryRouter'ы)
if (import.meta.env.DEV && window.location.pathname === "/dev") {
  import("./pages/DevPreviewPage").then(({ default: DevPreviewPage }) => {
    root.render(
      <StrictMode>
        <DevPreviewPage />
      </StrictMode>,
    );
  });
} else {
  root.render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}
