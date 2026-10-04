import pygame
import math

pygame.init()

info = pygame.display.Info()
WIDTH = max(640, info.current_w)
HEIGHT = max(480, info.current_h)

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("smooth skeleton reptile")
clock = pygame.time.Clock()

# NIGHT THEME — keeps the creature/movement unchanged.
# REFERENCE NIGHT THEME — dark indigo/blue with a soft purple-blue glow.
# The creature movement, speed, gait and size below are kept unchanged.
NIGHT_TOP = (5, 4, 20)
NIGHT_MID = (7, 3, 34)
NIGHT_BOTTOM = (17, 8, 60)
WHITE = (255, 255, 255)
CREATURE_HALO = (150, 155, 235)

background = None

def make_night_background(width, height):
    # Build the effect on a small surface, then scale it up. This keeps the
    # background smooth without making startup/resizing unnecessarily heavy.
    bw, bh = 240, 320
    surf = pygame.Surface((bw, bh))
    pixels = pygame.PixelArray(surf)

    cx, cy = bw * 0.48, bh * 0.80
    glow_r = bw * 0.95

    for y in range(bh):
        t = y / float(bh - 1)
        if t < 0.62:
            q = t / 0.62
            base = tuple(int(NIGHT_TOP[i] * (1 - q) + NIGHT_MID[i] * q) for i in range(3))
        else:
            q = (t - 0.62) / 0.38
            base = tuple(int(NIGHT_MID[i] * (1 - q) + NIGHT_BOTTOM[i] * q) for i in range(3))

        for x in range(bw):
            dx = (x - cx) / glow_r
            dy = (y - cy) / (bh * 0.78)
            d2 = dx * dx + dy * dy
            glow = max(0.0, 1.0 - d2)
            glow = glow * glow * 0.78

            # Purple/blue illumination inspired by the supplied reference.
            r = min(255, int(base[0] + 54 * glow))
            g = min(255, int(base[1] + 43 * glow))
            b = min(255, int(base[2] + 115 * glow))

            # Dark vignette toward the corners, especially the upper/right side.
            vx = (x - bw * 0.5) / (bw * 0.72)
            vy = (y - bh * 0.52) / (bh * 0.82)
            vignette = max(0.0, vx * vx + vy * vy - 0.28) * 0.20
            factor = max(0.56, 1.0 - vignette)

            pixels[x, y] = surf.map_rgb((int(r * factor), int(g * factor), int(b * factor)))

    del pixels
    return pygame.transform.smoothscale(surf, (width, height))

background = make_night_background(WIDTH, HEIGHT)

mouse_x = WIDTH * 0.85
mouse_y = HEIGHT * 0.80


def wrap_angle(a):
    return a - 2.0 * math.pi * math.floor(a / (2.0 * math.pi) + 0.5)


def distance(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)


def lerp_angle(current, target, amount):
    """Move smoothly from one angle to another without wrap-around jumps."""
    return current + wrap_angle(target - current) * amount


class Segment:
    def __init__(self, parent, size, rel_angle, angle_range, stiffness):
        self.parent = parent
        self.children = []
        self.size = float(size)
        self.rel_angle = float(rel_angle)
        self.def_angle = float(rel_angle)
        self.range = float(angle_range)
        self.stiffness = float(stiffness)

        parent.children.append(self)

        self.abs_angle = parent.abs_angle + self.rel_angle
        self.x = parent.x + math.cos(self.abs_angle) * self.size
        self.y = parent.y + math.sin(self.abs_angle) * self.size

    def update_relative(self, recursive=False, flex=True):
        self.rel_angle = wrap_angle(self.rel_angle)

        if flex:
            lo = self.def_angle - self.range / 2.0
            hi = self.def_angle + self.range / 2.0

            value = (
                (self.rel_angle - self.def_angle)
                / self.stiffness
                + self.def_angle
            )

            self.rel_angle = max(lo, min(hi, value))

        self.abs_angle = self.parent.abs_angle + self.rel_angle
        self.x = self.parent.x + math.cos(self.abs_angle) * self.size
        self.y = self.parent.y + math.sin(self.abs_angle) * self.size

        if recursive:
            for child in self.children:
                child.update_relative(True, flex)

    def follow(self, recursive=True):
        px = self.parent.x
        py = self.parent.y

        dx = self.x - px
        dy = self.y - py
        d = math.hypot(dx, dy)

        if d < 0.000001:
            target_abs = self.parent.abs_angle
        else:
            target_abs = math.atan2(dy, dx)

        # Gentle angle blending removes the tiny snapping feeling in the tail.
        desired_rel = wrap_angle(target_abs - self.parent.abs_angle)
        desired_rel = max(
            self.def_angle - self.range / 2.0,
            min(self.def_angle + self.range / 2.0, desired_rel)
        )

        # Higher stiffness = calmer, slower-looking segment response.
        blend = max(0.10, min(0.52, 0.85 / self.stiffness))
        self.rel_angle = lerp_angle(self.rel_angle, desired_rel, blend)
        self.update_relative(False, False)

        if recursive:
            for child in self.children:
                child.follow(True)

    def draw(self):
        start = (int(self.parent.x), int(self.parent.y))
        end = (int(self.x), int(self.y))

        # Bright outer halo + crisp white core, matching the luminous creature
        # look of the reference without changing any movement logic.
        pygame.draw.line(screen, CREATURE_HALO, start, end, 3)
        pygame.draw.line(screen, WHITE, start, end, 1)

        for child in self.children:
            child.draw()


class LimbSystem:
    def __init__(self, end, length, speed, creature):
        self.end = end
        self.length = max(1, int(length))
        self.speed = float(speed)
        self.creature = creature

        creature.systems.append(self)

        self.nodes = []
        node = end

        for _ in range(self.length):
            self.nodes.insert(0, node)
            node = node.parent

            if not isinstance(node, Segment):
                self.length = len(self.nodes)
                break

        self.hip = self.nodes[0].parent

    def move_to(self, x, y):
        self.nodes[0].update_relative(True, True)

        d = distance(x, y, self.end.x, self.end.y)
        remaining = max(0.0, d - self.speed)

        for node in reversed(self.nodes):
            ang = math.atan2(node.y - y, node.x - x)

            node.x = x + remaining * math.cos(ang)
            node.y = y + remaining * math.sin(ang)

            x = node.x
            y = node.y
            remaining = node.size

        for node in self.nodes:
            node.abs_angle = math.atan2(
                node.y - node.parent.y,
                node.x - node.parent.x
            )
            node.rel_angle = wrap_angle(
                node.abs_angle - node.parent.abs_angle
            )

            for child in node.children:
                if child not in self.nodes:
                    child.update_relative(True, False)

    def update(self, x, y):
        # The planted foot follows the creature, not the touch point directly.
        self.move_to(self.creature.x, self.creature.y)


class LegSystem(LimbSystem):
    def __init__(self, end, length, speed, creature, dist=4, gait_group=0, lateral=0.0, phase_offset=0.0):
        super().__init__(end, length, speed, creature)

        self.goal_x = end.x
        self.goal_y = end.y
        self.step = 0
        self.forwardness = 0.0
        self.gait_group = gait_group
        self.lateral = lateral
        self.phase_offset = phase_offset
        self.step_progress = 0.0
        self.start_x = self.goal_x
        self.start_y = self.goal_y

        self.reach = 0.9 * distance(
            self.end.x, self.end.y, self.hip.x, self.hip.y
        )

        rel = self.creature.abs_angle - math.atan2(
            self.end.y - self.hip.y,
            self.end.x - self.hip.x
        )
        rel = wrap_angle(rel)

        self.swing = -rel + (2 * (rel < 0) - 1) * math.pi / 2
        self.swing_offset = self.creature.abs_angle - self.hip.abs_angle

    def _plant_target(self):
        # A planted foot is placed slightly behind/ahead of the hip depending
        # on the current walking phase. This creates a real footfall instead
        # of making the legs simply wiggle while the body moves.
        forward = self.creature.abs_angle
        side_ang = forward + math.pi / 2.0

        # The foot target moves through a modest fore-aft window.
        stride = min(self.reach * 0.34, max(self.reach * 0.18, self.creature.speed * 4.0))
        phase = self.creature.walk_phase + self.phase_offset
        forward_offset = math.sin(phase) * stride

        base_ang = self.hip.abs_angle + self.swing + self.swing_offset
        base_x = self.hip.x + self.reach * 0.78 * math.cos(base_ang)
        base_y = self.hip.y + self.reach * 0.78 * math.sin(base_ang)

        return (
            base_x + math.cos(forward) * forward_offset + self.lateral * math.cos(side_ang),
            base_y + math.sin(forward) * forward_offset + self.lateral * math.sin(side_ang),
        )

    def update(self, x, y):
        # Feet stay planted while the body passes over them. When a foot has
        # fallen far enough behind, only its gait group is allowed to step.
        if self.step == 0:
            self.move_to(self.goal_x, self.goal_y)

            d = distance(self.end.x, self.end.y, self.goal_x, self.goal_y)
            can_step = (self.creature.gait_group == self.gait_group)

            if can_step and d > max(3.0, self.reach * 0.17) and self.creature.speed > 0.28:
                self.step = 1
                self.step_progress = 0.0
                self.start_x = self.end.x
                self.start_y = self.end.y
                self.goal_x, self.goal_y = self._plant_target()

        else:
            # Smooth swing: quick enough to keep up with the body, but with
            # a small lift so the foot visibly picks up and sets down.
            step_rate = max(0.075, min(0.22, self.speed / max(1.0, self.reach) * 1.45))
            self.step_progress = min(1.0, self.step_progress + step_rate)

            t = self.step_progress
            eased = t * t * (3.0 - 2.0 * t)

            x_now = self.start_x + (self.goal_x - self.start_x) * eased
            y_now = self.start_y + (self.goal_y - self.start_y) * eased

            # Lift perpendicular to travel, not along it.
            lift = math.sin(t * math.pi) * self.reach * 0.11
            x_now -= math.sin(self.creature.abs_angle) * lift
            y_now += math.cos(self.creature.abs_angle) * lift

            self.move_to(x_now, y_now)

            if self.step_progress >= 1.0:
                self.step = 0
                self.goal_x = self.end.x
                self.goal_y = self.end.y


class Creature:
    def __init__(
        self,
        x,
        y,
        angle,
        f_accel,
        f_fric,
        f_res,
        f_thresh,
        r_accel,
        r_fric,
        r_res,
        r_thresh
    ):
        self.x = float(x)
        self.y = float(y)
        self.abs_angle = float(angle)

        self.f_speed = 0.0
        self.f_accel = float(f_accel)
        self.f_fric = float(f_fric)
        self.f_res = float(f_res)
        self.f_thresh = float(f_thresh)

        self.r_speed = 0.0
        self.r_accel = float(r_accel)
        self.r_fric = float(r_fric)
        self.r_res = float(r_res)
        self.r_thresh = float(r_thresh)

        self.children = []
        self.systems = []
        self.speed = 0.0
        self.gait_distance = 0.0
        self.gait_group = 0
        self.walk_phase = 0.0

    def follow(self, x, y):
        d = distance(self.x, self.y, x, y)
        target_angle = math.atan2(y - self.y, x - self.x)

        # Faster again than the previous version, while keeping acceleration smooth.
        max_speed = self.f_accel
        desired_speed = min(max_speed, max(0.0, d - self.f_thresh) * 0.14)

        if self.systems:
            standing = sum(1 for system in self.systems if system.step == 0)
            desired_speed *= 0.88 + 0.12 * (standing / len(self.systems))

        speed_blend = 0.20
        self.f_speed += (desired_speed - self.f_speed) * speed_blend
        self.f_speed *= (1.0 - self.f_res)
        self.speed = max(0.0, self.f_speed - self.f_fric)

        # Advance a staggered multi-phase walking cycle from actual body travel.
        # With 4 groups, nearby legs do not all lift at once.
        if self.speed > 0.20:
            self.gait_distance += self.speed
            self.walk_phase = (self.walk_phase + self.speed * 0.075) % (2.0 * math.pi)
            if self.gait_distance >= 10.5:
                self.gait_distance -= 10.5
                self.gait_group = (self.gait_group + 1) % 4

        # Smooth turning with a small angular-speed cap prevents the head/body
        # from twitching when the finger changes direction quickly.
        dif = wrap_angle(target_angle - self.abs_angle)

        if d > self.f_thresh:
            target_turn = max(-self.r_accel, min(self.r_accel, dif * 0.20))
        else:
            target_turn = 0.0

        self.r_speed += (target_turn - self.r_speed) * 0.17
        self.r_speed *= (1.0 - self.r_res)

        if abs(self.r_speed) < self.r_fric:
            self.r_speed = 0.0

        self.abs_angle = wrap_angle(self.abs_angle + self.r_speed)

        self.x += self.speed * math.cos(self.abs_angle)
        self.y += self.speed * math.sin(self.abs_angle)

        # Body is built facing backward relative to the root, same as the
        # original creature construction.
        self.abs_angle += math.pi

        for child in self.children:
            child.follow(True)

        for system in self.systems:
            system.update(x, y)

        self.abs_angle -= math.pi
        self.draw()

    def draw(self):
        # Slightly larger head/root for the requested overall size increase.
        r = 5.0

        a1 = math.pi / 4 + self.abs_angle
        a2 = 7 * math.pi / 4 + self.abs_angle

        points = [
            (
                self.x + r * math.cos(a1),
                self.y + r * math.sin(a1)
            ),
            (
                self.x + r * math.sqrt(2) * math.cos(self.abs_angle),
                self.y + r * math.sqrt(2) * math.sin(self.abs_angle)
            ),
            (
                self.x + r * math.cos(a2),
                self.y + r * math.sin(a2)
            )
        ]

        int_points = [(int(x), int(y)) for x, y in points]
        pygame.draw.lines(screen, CREATURE_HALO, False, int_points, 4)
        pygame.draw.lines(screen, WHITE, False, int_points, 2)

        for child in self.children:
            child.draw()


def build_lizard(size, legs, tail):
    s = float(size)

    creature = Creature(
        WIDTH / 2,
        HEIGHT / 2,
        0,
        s * 7.4,      # quicker, natural walking/chasing speed
        s * 0.18,     # light friction
        0.16,         # less abrupt braking
        12,
        0.24,         # gentler turning
        0.010,
        0.18,
        0.12
    )

    spinal = creature

    # NECK
    for _ in range(6):
        spinal = Segment(
            spinal,
            s * 4,
            0,
            math.pi * 2 / 3,
            1.7
        )

        for side in (-1, 1):
            node = Segment(
                spinal,
                s * 3,
                side,
                0.08,
                2.8
            )

            for _ in range(3):
                node = Segment(
                    node,
                    s * 0.10,
                    -side * 0.10,
                    0.08,
                    3.0
                )

    # BODY + LEGS
    for leg_index in range(legs):
        if leg_index > 0:
            for _ in range(6):
                spinal = Segment(
                    spinal,
                    s * 4,
                    0,
                    1.571,
                    1.8
                )

                for side in (-1, 1):
                    node = Segment(
                        spinal,
                        s * 3,
                        side * 1.571,
                        0.08,
                        2.6
                    )

                    for _ in range(3):
                        node = Segment(
                            node,
                            s * 3,
                            -side * 0.25,
                            0.08,
                            2.8
                        )

        # LEGS
        for side in (-1, 1):
            node = Segment(
                spinal,
                s * 12,
                side * 0.785,
                0,
                8
            )

            node = Segment(
                node,
                s * 16,
                -side * 0.785,
                5.3,
                1.3
            )

            node = Segment(
                node,
                s * 16,
                side * 1.571,
                math.pi,
                2.2
            )

            # Keep toes stable instead of letting them fan too aggressively.
            for toe in range(4):
                Segment(
                    node,
                    s * 4,
                    (toe / 3 - 0.5) * 0.95,
                    0.07,
                    4.5
                )

            # Slower planted-foot repositioning = cleaner walking motion.
            LegSystem(
                node,
                3,
                s * 9.0,
                creature,
                4,
                gait_group=(leg_index * 2 + (1 if side > 0 else 0)) % 4,
                lateral=side * s * 2.0,
                phase_offset=((leg_index * 2 + (1 if side > 0 else 0)) * math.pi / 2.0)
            )

    # LONG TAIL — deliberately calmer than the original.
    for i in range(tail):
        spinal = Segment(
            spinal,
            s * 4,
            0,
            0.62,       # much less side-to-side whipping
            2.0
        )

        for side in (-1, 1):
            node = Segment(
                spinal,
                s * 3,
                side,
                0.055,
                3.2
            )

            tail_scale = (tail - i) / float(tail)

            for _ in range(3):
                node = Segment(
                    node,
                    s * 3 * tail_scale,
                    -side * 0.08,
                    0.055,
                    3.4
                )

    return creature


# Slightly larger than the original while staying mobile-friendly.
LEG_COUNT = 12
TAIL_COUNT = 48
SCALE = 11.0 / math.sqrt(LEG_COUNT)

creature = build_lizard(SCALE, LEG_COUNT, TAIL_COUNT)

running = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.VIDEORESIZE:
            WIDTH = max(480, event.w)
            HEIGHT = max(360, event.h)
            screen = pygame.display.set_mode(
                (WIDTH, HEIGHT),
                pygame.RESIZABLE
            )
            background = make_night_background(WIDTH, HEIGHT)

        elif event.type == pygame.MOUSEMOTION:
            mouse_x, mouse_y = event.pos

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mouse_x, mouse_y = event.pos

        elif event.type == pygame.FINGERDOWN:
            mouse_x = event.x * WIDTH
            mouse_y = event.y * HEIGHT

        elif event.type == pygame.FINGERMOTION:
            mouse_x = event.x * WIDTH
            mouse_y = event.y * HEIGHT

    screen.blit(background, (0, 0))

    creature.follow(mouse_x, mouse_y)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
