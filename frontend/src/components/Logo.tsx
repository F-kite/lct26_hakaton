import { Link } from "react-router-dom";
import logo from "../../public/Logo.svg"

export default function Logo() {
  return (
    <div className="flex items-center gap-2 select-none hover:cursor-pointer">
      <Link to={"/"}>
        <img src={logo} alt="ГАЗПРОМБАНК ТЕХ" />
      </Link>
    </div>
  );
}
