declare module "react-icons/fa" {
  import { IconBaseProps } from "react-icons";
  
  interface FaIconProps extends IconBaseProps {
    className?: string;
  }
  
  export const FaUser: React.ComponentType<FaIconProps>;
  export const FaCalendarAlt: React.ComponentType<FaIconProps>;
  export const FaGlobe: React.ComponentType<FaIconProps>;
  export const FaLink: React.ComponentType<FaIconProps>;
  export const FaChevronLeft: React.ComponentType<FaIconProps>;
  export const FaRegNewspaper: React.ComponentType<FaIconProps>;
  export const FaCheckCircle: React.ComponentType<FaIconProps>;
  export const FaExclamationCircle: React.ComponentType<FaIconProps>;
  export const FaQuestionCircle: React.ComponentType<FaIconProps>;
  export const FaArrowRight: React.ComponentType<FaIconProps>;
  export const FaNewspaper: React.ComponentType<FaIconProps>;
} 