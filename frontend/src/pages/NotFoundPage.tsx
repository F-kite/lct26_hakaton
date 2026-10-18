import { Link } from "react-router-dom";

import Logo from "../components/Logo";

export default function NotFoundPage() {
  return (
    <div className="animate-fade-in flex min-h-screen flex-col bg-neutral-100">
      <header className="px-6 pb-3 pt-7 sm:px-10 xl:px-20">
        <Logo />
      </header>
      <main className="flex flex-1 flex-col items-center justify-center text-center">
        {/* макет: 3 символа по 220px, gap 20px, высота 230px, opacity 10% */}
        <div
          role="img"
          aria-label="404"
          className="flex items-center gap-5 font-display text-[220px] leading-57.5 font-medium text-primary opacity-10 select-none"
        >
          <span aria-hidden>4</span>
          <span aria-hidden>0</span>
          <span aria-hidden>4</span>
        </div>
        <h1 className="mt-4 text-5xl font-bold text-neutral-950">Страница не найдена</h1>
        <p className="mx-auto mt-5 max-w-lg text-lg text-neutral-600">
          Возможно, страница была перемещена, удалена или указан неверный адрес.
        </p>
        <Link
          to="/"
          className="mt-7 rounded-full bg-primary px-8 py-3 text-base text-white hover:bg-link-hover"
        >
          На главную
        </Link>
      </main>
    </div>
  );
}
