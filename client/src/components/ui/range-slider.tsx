import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cn } from "@/lib/utils";

const RangeSlider = React.forwardRef<typeof SliderPrimitive.Root, any>(
  ({ className, value = [0, 100], onValueChange, ...props }, ref) => {
    const values = Array.isArray(value) ? value : [value];

    return (
      <SliderPrimitive.Root
        className={cn("relative flex w-full touch-none select-none items-center", className)}
        value={values}
        onValueChange={onValueChange}
        {...props}
      >
        <SliderPrimitive.Track className="relative h-2 w-full grow overflow-hidden rounded-full bg-secondary">
          <SliderPrimitive.Range className="absolute h-full bg-primary" />
        </SliderPrimitive.Track>

        {values.map((_, i) => (
          <SliderPrimitive.Thumb
            key={i}
            className="block h-5 w-5 rounded-full border-2 border-primary bg-background ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
          />
        ))}
      </SliderPrimitive.Root>
    );
  }
);

RangeSlider.displayName = SliderPrimitive.Root.displayName;

export { RangeSlider };

