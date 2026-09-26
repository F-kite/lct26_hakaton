import { Link } from "react-router-dom";

import Logo from "../components/Logo";

export default function NotFoundPage() {
  return (
    <div className="animate-fade-in flex min-h-screen flex-col bg-neutral-100">
      <header className="px-6 py-6 sm:px-10">
        <Logo />
      </header>
      <main className="flex flex-1 flex-col items-center justify-center text-center">
        <div className="font-display text-8xl font-bold text-neutral-200">404</div>
        <h1 className="mt-4 text-2xl font-bold text-neutral-950">Страница не найдена</h1>
        <p className="mt-2 text-neutral-500">
          Возможно, страница была перемещена, удалена или указан неверный адрес.
        </p>
        <Link
          to="/"
          className="mt-6 rounded-full bg-primary px-6 py-2.5 text-sm text-white hover:bg-link-hover"
        >
          На главную
        </Link>
      </main>
    </div>
  );
}
