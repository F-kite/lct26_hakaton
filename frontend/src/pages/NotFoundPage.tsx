import { Link } from "react-router-dom";

import Logo from "../components/Logo";

export default function NotFoundPage() {
  return (
    <div className="animate-fade-in flex min-h-screen flex-col bg-neutral-100">
      <header className="px-6 pb-3 pt-7 sm:px-10 xl:px-20">
        <Logo />
      </header>
      <main className="flex flex-1 flex-col items-center justify-center text-center">
        <div className="font-display text-9xl font-bold text-link-hover ">404</div>
        <h1 className="mt-4 text-4xl font-bold text-neutral-950">Страница не найдена</h1>
        <p className="mx-auto mt-2 max-w-lg text-xl text-neutral-600">
          Возможно, страница была перемещена, удалена или указан неверный адрес.
        </p>
        <Link
          to="/"
          className="mt-7 rounded-full bg-primary px-8 py-3 text-md text-white hover:bg-link-hover"
        >
          На главную
        </Link>
      </main>
    </div>
  );
}
