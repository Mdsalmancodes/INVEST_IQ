import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef } from "react";

import { cn } from "../../lib/cn";

/**
 * Button primitive — wraps Radix Slot (for `asChild` composition) + cva for
 * variant styling, per Document 2 §6.3's "wrapping shadcn/Radix" pattern.
 * Touch target sizing follows Document 2 §6.1a's 44x44px minimum on the
 * default/lg sizes; `sm` is only for desktop-dense contexts, never the sole
 * interactive target on a touch surface.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium " +
    "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary " +
    "disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-primary text-white hover:bg-primary-600",
        secondary: "bg-surface text-text-primary border border-primary-100 hover:bg-primary-50",
        ghost: "hover:bg-primary-50 text-text-primary",
        destructive: "bg-danger text-white hover:opacity-90",
      },
      size: {
        default: "h-11 px-4 py-2", // 44px min height — Document 2 §6.1a touch target rule
        sm: "h-9 px-3",
        lg: "h-12 px-6 text-base",
        icon: "h-11 w-11", // square touch target, not a shrunken icon-only button
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size, className }))}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
