import logo from "../../public/Logo.svg"

export default function Logo() {
  return (
    <div className="flex items-center gap-2 select-none">
      {/* <svg width="32" height="28" viewBox="0 0 32 28" fill="none" aria-hidden="true">
        <path d="M16 0 L32 14 L16 28 L0 14 Z" fill="none" stroke="#0F0F0F" strokeWidth="2" />
        <path d="M4 14 L16 4 L16 24 Z" fill="#0F0F0F" />
      </svg>
      <div className="leading-[0.95]">
        <div className="font-display font-bold text-[15px] tracking-tight text-neutral-950">
          ГАЗПРОМБАНК
        </div>
        <div className="font-display font-bold text-[15px] tracking-tight text-neutral-950">ТЕХ</div>
      </div> */}
      <img src={logo} alt="ГАЗПРОМБАНК ТЕХ" />
    </div>
  );
}
