// Apache-2.0: AhakeyAI/desktop c518f9f62994d465843d19cf84d782e2d2e04a05.
// APP/sub_main/psk_ws2812.c animation logic retained; hardware output is in main.cpp.
#include "OriginalLights.h"
namespace aha { namespace original {
constexpr int LED_NUM=8;
struct RGB {uint8_t blue,green,red,alpha;};
union color_t {uint32_t hex; RGB rgb;};
static color_t ws2812_list[LED_NUM]{};
enum ws2812_mode_e {
    WS2812_OFF = 0x0, // all led black (off)
    WS2812_SINGLE_MOVE,
    WS2812_RAINBOW_MOVE,
    WS2812_RAINBOW_WAVE,
    WS2812_RAINBOW_WAVE_SLOW,
    WS2812_BREATHING,
    WS2812_MIDDLE_LIGHT,
    WS2812_TYPING_RIPPLE,
    WS2812_COMET,
    WS2812_SCAN_BAR,
    WS2812_PULSE_CENTER,
    WS2812_WARNING_BLINK,
    WS2812_SUCCESS_SWEEP,
    WS2812_BLUE_THINKING,
    WS2812_LOW_BATTERY,
    WS2812_CHARGING_FLOW,
    WS2812_APPROVAL_WAIT,

};

static void ws2812_clear_all(void)
{
    for (int i = 0; i < LED_NUM; i++) {
        ws2812_list[i].hex = 0;
    }
}

static void ws2812_set_rgb(uint8_t index, uint8_t red, uint8_t green, uint8_t blue, uint8_t alpha)
{
    if (index >= LED_NUM)
        return;
    ws2812_list[index].rgb.red   = red;
    ws2812_list[index].rgb.green = green;
    ws2812_list[index].rgb.blue  = blue;
    ws2812_list[index].rgb.alpha = alpha;
}

static uint8_t ws2812_triangle(uint8_t phase)
{
    return phase < 128 ? phase * 2 : (255 - phase) * 2;
}
void ws2812_display(enum ws2812_mode_e mode, uint32_t COLOR_HEX)
{
    static uint8_t led_position = 0;
    static int8_t  direction    = 1; // 1 = forward, -1 = backward

    switch (mode) {
    case WS2812_OFF:
        // Turn off all LEDs
        for (int i = 0; i < LED_NUM; i++) {
            ws2812_list[i].hex = 0;
        }
        break;

    case WS2812_SINGLE_MOVE:
        // Clear all LEDs first
        for (int i = 0; i < LED_NUM; i++) {
            ws2812_list[i].hex = 0;
        }

        // Set main LED at full brightness
        // #define COLOR_HEX 0xff3333
        ws2812_list[led_position].hex       = COLOR_HEX;
        ws2812_list[led_position].rgb.alpha = 160;

        // Set adjacent LEDs at 60% brightness
        if (led_position > 0) {
            ws2812_list[led_position - 1].hex       = COLOR_HEX;
            ws2812_list[led_position - 1].rgb.alpha = 55;
        }
        if (led_position < LED_NUM - 1) {
            ws2812_list[led_position + 1].hex       = COLOR_HEX;
            ws2812_list[led_position + 1].rgb.alpha = 55;
        }

        // Set LEDs 2 positions away at 30% brightness
        if (led_position > 1) {
            ws2812_list[led_position - 2].hex       = COLOR_HEX;
            ws2812_list[led_position - 2].rgb.alpha = 30; // 30% of 255
        }
        if (led_position < LED_NUM - 2) {
            ws2812_list[led_position + 2].hex       = COLOR_HEX;
            ws2812_list[led_position + 2].rgb.alpha = 30; // 30% of 255
        }

        // Update position for next iteration
        led_position += direction;

        // Bounce back when reaching the end
        if (led_position >= LED_NUM - 1) {
            led_position = LED_NUM - 1;
            direction    = -1;
        } else if (led_position <= 0) {
            led_position = 0;
            direction    = 1;
        }
        break;

    case WS2812_RAINBOW_WAVE:
    case WS2812_RAINBOW_WAVE_SLOW:
    case WS2812_RAINBOW_MOVE: {
        static uint8_t hue_offset = 0;

        // Create rainbow wave across all LEDs
        for (int i = 0; i < LED_NUM; i++) {
            // Calculate hue for this LED (0-255 range)
            // Spread rainbow across LEDs and add time-based offset for animation
            uint8_t hue = (i * 256 / LED_NUM + hue_offset) & 0xFF;

            // Simple HSV to RGB conversion (S=255, V=255)
            uint8_t region    = hue / 43; // 0-5
            uint8_t remainder = (hue - (region * 43)) * 6;

            uint8_t r = 0, g = 0, b = 0;

            switch (region) {
            case 0:
                r = 120;
                g = remainder / 2;
                b = 0;
                break;
            case 1:
                r = (255 - remainder) / 2;
                g = 120;
                b = 0;
                break;
            case 2:
                r = 0;
                g = 120;
                b = remainder / 2;
                break;
            case 3:
                r = 0;
                g = (255 - remainder) / 2;
                b = 120;
                break;
            case 4:
                r = remainder / 2;
                g = 0;
                b = 120;
                break;
            default:
                r = 120;
                g = 0;
                b = (255 - remainder) / 2;
                break;
            }

            ws2812_list[i].rgb.red   = r;
            ws2812_list[i].rgb.green = g;
            ws2812_list[i].rgb.blue  = b;
            ws2812_list[i].rgb.alpha = 120;
        }

        // Advance the wave animation
        if (mode == WS2812_RAINBOW_WAVE_SLOW)
            hue_offset -= 2;
        else
            hue_offset -= 10;
        if (mode == WS2812_RAINBOW_MOVE) {
            for (int i = 0; i < LED_NUM; i++)
                ws2812_list[i].rgb.alpha = 1;
            ws2812_list[led_position].rgb.alpha = 150;

            if (led_position > 0) {
                ws2812_list[led_position - 1].rgb.alpha = 55;
            }
            if (led_position < LED_NUM - 1) {
                ws2812_list[led_position + 1].rgb.alpha = 55;
            }

            // Set LEDs 2 positions away at 30% brightness
            if (led_position > 1) {
                ws2812_list[led_position - 2].rgb.alpha = 30; // 30% of 255
            }
            if (led_position < LED_NUM - 2) {
                ws2812_list[led_position + 2].rgb.alpha = 30; // 30% of 255
            }

            // Update position for next iteration
            led_position += direction;

            // Bounce back when reaching the end
            if (led_position >= LED_NUM - 1) {
                led_position = LED_NUM - 1;
                direction    = -1;
            } else if (led_position <= 0) {
                led_position = 0;
                direction    = 1;
            }
        }
    } break;

    case WS2812_BREATHING: {
        static uint8_t brightness = 0;
        static int8_t  fade_dir   = 1; // 1 = fade in, -1 = fade out

                                       // Define breathing color (soft blue)
        // #define COLOR_HEX 0x3264ff

        // Set all LEDs to the same color with current brightness
        for (int i = 0; i < LED_NUM; i++) {
            ws2812_list[i].hex       = COLOR_HEX;
            ws2812_list[i].rgb.alpha = brightness;
        }

        // Update brightness for breathing effect
        brightness += fade_dir * 8;

        // Reverse direction at min/max brightness
        if (brightness >= 140) {
            brightness = 140;
            fade_dir   = -1;
        } else if (brightness <= 20) {
            brightness = 20;
            fade_dir   = 1;
        }
    } break;
    case WS2812_MIDDLE_LIGHT: {
        const uint8_t light[4] = {1, 15, 60, 130};
        for (int i = 0; i < LED_NUM / 2; i++) {
            ws2812_list[i].hex                     = COLOR_HEX;
            ws2812_list[i].rgb.alpha               = light[i];
            ws2812_list[LED_NUM - 1 - i].hex       = COLOR_HEX;
            ws2812_list[LED_NUM - 1 - i].rgb.alpha = light[i];
        }

    } break;

    case WS2812_TYPING_RIPPLE: {
        static uint8_t ripple_phase = 0;
        const int      center_left  = LED_NUM / 2 - 1;
        const int      center_right = LED_NUM / 2;
        ws2812_clear_all();
        for (int i = 0; i < LED_NUM; i++) {
            int distance_left  = i > center_left ? i - center_left : center_left - i;
            int distance_right = i > center_right ? i - center_right : center_right - i;
            int distance       = distance_left < distance_right ? distance_left : distance_right;
            int wave           = ripple_phase - distance * 28;
            if (wave >= 0 && wave < 80) {
                uint8_t alpha = wave < 32 ? wave * 4 : (80 - wave) * 2;
                ws2812_set_rgb(i, 0x08, 0x50, 0x60, alpha);
            }
        }
        ripple_phase += 12;
        if (ripple_phase >= 150)
            ripple_phase = 0;
    } break;

    case WS2812_COMET: {
        static uint8_t comet_pos = 0;
        static int8_t  comet_dir = 1;
        const uint8_t  tail[5]   = {160, 90, 45, 20, 8};
        ws2812_clear_all();
        for (int i = 0; i < LED_NUM; i++) {
            int distance = i > comet_pos ? i - comet_pos : comet_pos - i;
            if (distance < 5)
                ws2812_set_rgb(i, 0x80, 0x28, 0x10, tail[distance]);
        }
        comet_pos += comet_dir;
        if (comet_pos >= LED_NUM - 1) {
            comet_pos = LED_NUM - 1;
            comet_dir = -1;
        } else if (comet_pos == 0) {
            comet_dir = 1;
        }
    } break;

    case WS2812_SCAN_BAR: {
        static uint8_t scan_pos = 0;
        static int8_t  scan_dir = 1;
        ws2812_clear_all();
        ws2812_set_rgb(scan_pos, 0x40, 0x40, 0x50, 140);
        if (scan_pos + 1 < LED_NUM)
            ws2812_set_rgb(scan_pos + 1, 0x08, 0x50, 0x60, 80);
        if (scan_pos > 0)
            ws2812_set_rgb(scan_pos - 1, 0x08, 0x50, 0x60, 35);
        scan_pos += scan_dir;
        if (scan_pos >= LED_NUM - 1) {
            scan_pos = LED_NUM - 1;
            scan_dir = -1;
        } else if (scan_pos == 0) {
            scan_dir = 1;
        }
    } break;

    case WS2812_PULSE_CENTER: {
        static uint8_t pulse_phase = 0;
        uint8_t        core        = 35 + ws2812_triangle(pulse_phase) / 4;
        uint8_t        side        = core / 3;
        ws2812_clear_all();
        ws2812_set_rgb(3, 0x10, 0x28, 0x80, core);
        ws2812_set_rgb(4, 0x10, 0x28, 0x80, core);
        ws2812_set_rgb(2, 0x10, 0x28, 0x80, side);
        ws2812_set_rgb(5, 0x10, 0x28, 0x80, side);
        pulse_phase += 6;
    } break;

    case WS2812_WARNING_BLINK: {
        static uint8_t warn_tick = 0;
        uint8_t        on        = (warn_tick % 18) < 5 || ((warn_tick + 8) % 18) < 3;
        for (int i = 0; i < LED_NUM; i++) {
            if (on)
                ws2812_set_rgb(i, 0x80, i % 2 ? 0x10 : 0x30, 0x00, 150);
            else
                ws2812_set_rgb(i, 0x18, 0x00, 0x00, 15);
        }
        warn_tick++;
    } break;

    case WS2812_SUCCESS_SWEEP: {
        static uint8_t success_pos = 0;
        ws2812_clear_all();
        for (int i = 0; i < LED_NUM; i++) {
            if (i <= success_pos)
                ws2812_set_rgb(i, 0x08, 0x70, 0x24, 100);
            if (i == success_pos)
                ws2812_set_rgb(i, 0x30, 0x70, 0x30, 120);
        }
        success_pos++;
        if (success_pos >= LED_NUM + 5)
            success_pos = 0;
    } break;

    case WS2812_BLUE_THINKING: {
        static uint8_t think_phase = 0;
        for (int i = 0; i < LED_NUM; i++) {
            uint8_t alpha = 20 + ws2812_triangle(think_phase + i * 24) / 4;
            ws2812_set_rgb(i, 0x08, 0x20, 0x80, alpha);
        }
        think_phase += 5;
    } break;

    case WS2812_LOW_BATTERY: {
        static uint8_t low_tick = 0;
        uint8_t        edge_on  = (low_tick % 24) < 8;
        ws2812_clear_all();
        ws2812_set_rgb(0, 0x80, 0x00, 0x00, edge_on ? 150 : 25);
        ws2812_set_rgb(LED_NUM - 1, 0x80, 0x00, 0x00, edge_on ? 150 : 25);
        for (int i = 1; i < LED_NUM - 1; i++)
            ws2812_set_rgb(i, 0x18, 0x00, 0x00, edge_on ? 20 : 8);
        low_tick++;
    } break;

    case WS2812_CHARGING_FLOW: {
        static uint8_t charge_step = 0;
        uint8_t        fill        = charge_step % (LED_NUM + 4);
        ws2812_clear_all();
        for (int i = 0; i < LED_NUM; i++) {
            if (i < fill)
                ws2812_set_rgb(i, 0x08, 0x70, 0x28, 100);
            else
                ws2812_set_rgb(i, 0x00, 0x18, 0x08, 12);
        }
        if (fill < LED_NUM)
            ws2812_set_rgb(fill, 0x30, 0x70, 0x30, 120);
        charge_step++;
    } break;

    case WS2812_APPROVAL_WAIT: {
        static uint8_t approval_phase = 0;
        uint8_t        breath         = 30 + ws2812_triangle(approval_phase) / 4;
        for (int i = 0; i < LED_NUM; i++)
            ws2812_set_rgb(i, 0x80, 0x30, 0x08, breath);
        if ((approval_phase % 64) < 10) {
            ws2812_set_rgb(3, 0x70, 0x60, 0x30, 120);
            ws2812_set_rgb(4, 0x70, 0x60, 0x30, 120);
        }
        approval_phase += 4;
    } break;
    default:
        break;
    }
}

} // original
void originalLightFrame(uint8_t effect, uint8_t brightness, LightRGB (&out)[8]) {
 original::ws2812_display(static_cast<original::ws2812_mode_e>(effect),0x102080);
 for (unsigned i=0;i<8;i++) {
  const auto c=original::ws2812_list[i].rgb;
  const uint16_t level=c.alpha ? (uint16_t(c.alpha)*brightness)>>8 : brightness;
  out[i]={uint8_t((uint16_t(c.red)*level)>>8),uint8_t((uint16_t(c.green)*level)>>8),uint8_t((uint16_t(c.blue)*level)>>8)};
 }
}
} // aha
