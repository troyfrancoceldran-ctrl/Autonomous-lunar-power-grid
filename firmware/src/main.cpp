// main.cpp — the board-specific wrapper. The ONLY file here that knows it is
// running on an ESP32.
//
// controller.cpp holds the policy and includes no framework header, so it
// compiles on the host and is held to the Python original's decisions by
// firmware/test/test_controller.cpp. This file does nothing but move numbers
// across a wire. Keeping that boundary is what makes the claim "the same
// controller, on hardware" checkable rather than merely asserted.
//
//==============================================================================
// THE PROTOCOL
//==============================================================================
// Line-based ASCII, host-initiated, one exchange per simulation tick. Text
// rather than packed binary on purpose: it can be read in a serial monitor
// with no tooling, which is worth more than the bandwidth on a 1440-tick run.
//
//   host -> board   ID
//   board -> host   LUNAR B03 <proto> <max_loads>
//
//   host -> board   R                              reset the dwell timers
//   board -> host   OK
//
//   host -> board   T <t_h> <soc> <headroom_w> <n> <p s d> <p s d> ...
//   board -> host   A <index> <shed>               index -1 means "no action"
//
// Every reply is exactly one line, so the host can read to a newline and never
// has to guess how much is coming.
#include <Arduino.h>

#include "controller.hpp"

// The thresholds are compiled in rather than sent. They are POLICY, and policy
// living on the board is the whole point of putting the controller there; a
// host that could set them each tick would be the controller.
#ifndef SOC_SHED_THRESHOLD
#define SOC_SHED_THRESHOLD 0.30
#endif
#ifndef SOC_RESTORE_THRESHOLD
#define SOC_RESTORE_THRESHOLD 0.45
#endif
#ifndef MIN_ACTION_DWELL_HOURS
#define MIN_ACTION_DWELL_HOURS 3.0
#endif

static lunar::Controller g_controller(SOC_SHED_THRESHOLD,
                                    SOC_RESTORE_THRESHOLD,
                                    MIN_ACTION_DWELL_HOURS);

static char g_line[1024];

/// Read one newline-terminated line. Returns its length, or -1 if none is
/// ready. Non-blocking so the watchdog is never starved.
static int read_line() {
    static int len = 0;
    while (Serial.available() > 0) {
        const int c = Serial.read();
        if (c < 0) break;
        if (c == '\n' || c == '\r') {
            if (len == 0) continue;            // tolerate CRLF and blank lines
            g_line[len] = '\0';
            const int out = len;
            len = 0;
            return out;
        }
        if (len < static_cast<int>(sizeof(g_line)) - 1) {
            g_line[len++] = static_cast<char>(c);
        } else {
            len = 0;                            // overlong line: drop it whole
        }
    }
    return -1;
}

static void handle_tick(char *body) {
    char *save = nullptr;
    const double t = atof(strtok_r(body, " ", &save));
    const double soc = atof(strtok_r(nullptr, " ", &save));
    const double headroom = atof(strtok_r(nullptr, " ", &save));
    const char *count_tok = strtok_r(nullptr, " ", &save);
    int count = count_tok ? atoi(count_tok) : 0;
    if (count > lunar::MAX_LOADS) count = lunar::MAX_LOADS;

    lunar::LoadView loads[lunar::MAX_LOADS];
    int parsed = 0;
    for (int i = 0; i < count; ++i) {
        const char *p = strtok_r(nullptr, " ", &save);
        const char *s = strtok_r(nullptr, " ", &save);
        const char *d = strtok_r(nullptr, " ", &save);
        if (!p || !s || !d) break;              // truncated line: use what came
        loads[i].priority = atoi(p);
        loads[i].shed = atoi(s) != 0;
        loads[i].demand_w = atof(d);
        ++parsed;
    }

    const lunar::Action a =
        g_controller.update(t, soc, headroom, loads, parsed);
    Serial.printf("A %d %d\n", a.index, a.shed ? 1 : 0);
}

void setup() {
    Serial.begin(115200);
    Serial.setTimeout(50);
    // No banner on boot. The host asks with ID when it is ready, and an
    // unsolicited line would have to be skipped past by every reader.
}

void loop() {
    const int len = read_line();
    if (len <= 0) return;

    switch (g_line[0]) {
        case 'T':
            handle_tick(g_line + 1);
            break;
        case 'R':
            g_controller.reset();
            Serial.print("OK\n");
            break;
        case 'I':
            Serial.printf("LUNAR B03 1 %d\n", lunar::MAX_LOADS);
            break;
        default:
            Serial.print("ERR\n");
            break;
    }
}
