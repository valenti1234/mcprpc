package io.mcprpc.automesh.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Expose {
    String name() default "";
    String description() default "";
    String[] tags() default {};
    String[] roles() default {};
    String version() default "0.1.0";
    InputMode inputMode() default InputMode.OBJECT;
    String[] parameters() default {};
    int costCpuWeight() default -1;
}
