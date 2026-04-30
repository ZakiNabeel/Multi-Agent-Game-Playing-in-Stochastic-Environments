import random
import math
import copy
import itertools
import dearpygui.dearpygui as dpg
import threading
import time

class Agent:
    def __init__(self, agent_id):
        self.id = agent_id
        self.energy = 20  # Both units share this pool
        self.score = 0
        self.units = []   # Will store (x, y) coordinates of the agent's 2 units
        self.disabled_turns = {} # Tracks if a unit is disabled by a mine

    def can_act(self):
        return self.energy > 0

class Cell:
    def __init__(self, cell_type):
        self.type = cell_type # '.', 'X', 'F', 'M', or agent ID ('A', 'B', 'C')
        self.defense_value = 0
        if cell_type == 'F':
            self.defense_value = 2 # Fortress base defense[cite: 1]
        elif cell_type in ['A', 'B', 'C']:
            self.defense_value = 1 # Regular owned cell base defense[cite: 1]

class GameState:
    def __init__(self, n, m):
        self.n = n
        self.m = m
        self.grid = [[Cell('.') for _ in range(m)] for _ in range(n)]
        self.agents = {'A': Agent('A'), 'B': Agent('B'), 'C': Agent('C')}
        
        # 9-Sided Die Combat Probabilities[cite: 1]
        self.combat_outcomes = [
            'fail_energy', # Faces 1, 2
            'fail',        # Face 3
            'partial',     # Faces 4, 5
            'partial_adv', # Face 6
            'full',        # Faces 7, 8
            'critical'     # Face 9
        ]
        self.combat_weights = [0.20, 0.15, 0.16, 0.12, 0.26, 0.11]

        # Minefield Probabilities[cite: 1]
        self.mine_outcomes = ['safe', 'drain', 'disable', 'detonate']
        self.mine_weights = [0.40, 0.30, 0.20, 0.10]

    def trigger_minefield(self, agent_id, unit_idx, pos):
        """Resolves the 4-sided minefield chance event[cite: 1]."""
        outcome = random.choices(self.mine_outcomes, weights=self.mine_weights, k=1)[0]
        agent = self.agents[agent_id]
        
        if outcome == 'drain':
            agent.energy = max(0, agent.energy - 3)
        elif outcome == 'disable':
            agent.disabled_turns[unit_idx] = 2
        elif outcome == 'detonate':
            agent.energy = max(0, agent.energy - 5)
            x, y = pos
            self.grid[x][y].type = 'X' # Becomes permanent obstacle[cite: 1]
            
        return outcome

    def resolve_combat(self, attacker_id, target_pos, is_move_action=False):
        """Resolves the 9-sided die combat system"""
        outcome = random.choices(self.combat_outcomes, weights=self.combat_weights, k=1)[0]
        attacker = self.agents[attacker_id]
        tx, ty = target_pos
        target_cell = self.grid[tx][ty]
        
        if outcome == 'fail_energy':
            attacker.energy = max(0, attacker.energy - 1) # Additional -1 energy[cite: 1]
            
        elif outcome in ['partial', 'partial_adv']:
            target_cell.type = '.' # Cell becomes neutral[cite: 1]
            target_cell.defense_value = 0
            if outcome == 'partial_adv' and is_move_action:
                return 'advance' # Attacker moves into empty cell[cite: 1]
                
        elif outcome in ['full', 'critical']:
            target_cell.defense_value -= 1 # Reduce defense[cite: 1]
            if target_cell.defense_value <= 0:
                target_cell.type = attacker_id # Captured!
                target_cell.defense_value = 1  
                if outcome == 'critical':
                    attacker.score += 2 # Critical hit bonus[cite: 1]
                if is_move_action:
                    return 'advance'
                    
        return outcome

    def execute_action(self, agent_id, unit_idx, action, target_pos=None):
        """Executes one of the 4 valid actions for a given unit."""
        agent = self.agents[agent_id]
        
        # Check if unit is disabled or out of energy
        if agent.energy <= 0 or agent.disabled_turns.get(unit_idx, 0) > 0:
            action = 'Wait' # Forced to wait[cite: 1]
            if agent.disabled_turns.get(unit_idx, 0) > 0:
                agent.disabled_turns[unit_idx] -= 1

        agent.energy -= 1 # Base cost for any action[cite: 1]
        
        if action == 'Wait':
            return "Waited."

        ux, uy = agent.units[unit_idx]
        tx, ty = target_pos

        if action == 'Move':
            target_cell = self.grid[tx][ty]
            
            if target_cell.type == '.':
                target_cell.type = agent_id # Capture empty cell immediately[cite: 1]
                target_cell.defense_value = 1
                agent.units[unit_idx] = (tx, ty)
            elif target_cell.type in ['A', 'B', 'C'] and target_cell.type != agent_id:
                result = self.resolve_combat(agent_id, target_pos, is_move_action=True)
                if result == 'advance':
                    agent.units[unit_idx] = (tx, ty) # Move in after successful combat
            elif target_cell.type == 'M':
                agent.units[unit_idx] = (tx, ty)
                self.trigger_minefield(agent_id, unit_idx, (tx, ty)) # Trigger mine[cite: 1]
                
        elif action == 'Attack':
            target_cell = self.grid[tx][ty]
            if target_cell.type in ['A', 'B', 'C'] and target_cell.type != agent_id:
                self.resolve_combat(agent_id, target_pos, is_move_action=False)
                
        elif action == 'Fortify':
            target_cell = self.grid[tx][ty]
            # Must own cell to fortify, max defense is 3[cite: 1]
            if target_cell.type == agent_id and target_cell.defense_value < 3:
                target_cell.defense_value += 1

        return f"Executed {action} on {target_pos}."
    

class AI_Agent:
    def __init__(self, agent_id, max_depth):
        self.agent_id = agent_id
        self.max_depth = max_depth
        # Stats tracking for the per-move report
        self.nodes_explored = 0
        self.nodes_pruned = 0

    def get_best_move(self, current_state):
        """Entry point for the AI to pick its move."""
        self.nodes_explored = 0
        self.nodes_pruned = 0
        
        best_value = -math.inf
        best_action = None
        
        # Initial Alpha-Beta bounds
        alpha = -math.inf
        beta = math.inf

        # Generate all possible legal moves for this agent's units
        possible_moves = self.generate_legal_moves(current_state, self.agent_id)

        for move in possible_moves:
            # Simulate the move being chosen (creates a Chance Node scenario)
            simulated_state = self.simulate_move(current_state, move)
            
            # The next layer is a CHANCE node to resolve the move's stochastic outcome[cite: 1]
            move_value = self.expectiminimax(
                state=simulated_state, 
                depth=self.max_depth, 
                current_agent=self.agent_id, 
                maximizing_agent=self.agent_id, 
                alpha=alpha, 
                beta=beta, 
                is_chance_node=True
            )

            if move_value > best_value:
                best_value = move_value
                best_action = move

            alpha = max(alpha, best_value)

        return best_action, best_value

    def expectiminimax(self, state, depth, current_agent, maximizing_agent, alpha, beta, is_chance_node):
        self.nodes_explored += 1

        # Base Case: Reached depth limit or game is over[cite: 1]
        if depth == 0 or self.is_terminal_state(state):
            return self.evaluation_function(state, maximizing_agent)

        # ---------------------------------------------------------
        # CHANCE NODE LAYER
        # ---------------------------------------------------------
        if is_chance_node:
            expected_value = 0
            
            # Fetch probabilities based on the action taken (e.g., 9-sided die)[cite: 1]
            chance_outcomes = self.get_chance_outcomes(state)
            
            for prob, outcome_state in chance_outcomes:
                # Next agent's turn begins after chance resolution
                next_agent = self.get_next_agent(current_agent)
                
                # Recursively call standard MAX/MIN node. 
                # Note: Depth decreases only after a full round, or per agent ply depending on your preference.
                # Assuming depth decreases per ply here.
                value = self.expectiminimax(
                    outcome_state, depth - 1, next_agent, maximizing_agent, alpha, beta, False
                )
                expected_value += prob * value
                
                # CRITICAL: No Alpha-Beta pruning happens in Chance nodes![cite: 1]
                # All branches must be evaluated for correct probability weighting[cite: 1].
                
            return expected_value

        # ---------------------------------------------------------
        # MAX NODE LAYER (It is our turn)
        # ---------------------------------------------------------
        elif current_agent == maximizing_agent:
            max_eval = -math.inf
            possible_moves = self.generate_legal_moves(state, current_agent)
            
            for move in possible_moves:
                outcome_state = self.simulate_move(state, move)
                eval_score = self.expectiminimax(
                    outcome_state, depth, current_agent, maximizing_agent, alpha, beta, True
                )
                
                max_eval = max(max_eval, eval_score)
                alpha = max(alpha, eval_score)
                
                # Alpha-Beta Pruning[cite: 1]
                if beta <= alpha:
                    self.nodes_pruned += 1
                    break # Prune the remaining branches
                    
            return max_eval

        # ---------------------------------------------------------
        # MIN NODE LAYER (It is an opponent's turn)
        # ---------------------------------------------------------
        else:
            min_eval = math.inf
            possible_moves = self.generate_legal_moves(state, current_agent)
            
            for move in possible_moves:
                outcome_state = self.simulate_move(state, move)
                eval_score = self.expectiminimax(
                    outcome_state, depth, current_agent, maximizing_agent, alpha, beta, True
                )
                
                min_eval = min(min_eval, eval_score)
                beta = min(beta, eval_score)
                
                # Alpha-Beta Pruning[cite: 1]
                if beta <= alpha:
                    self.nodes_pruned += 1
                    break # Prune the remaining branches
                    
            return min_eval
        

    def get_next_agent(self, current_agent):
        """Cycles the turn order: A -> B -> C -> A."""
        agents = ['A', 'B', 'C']
        current_idx = agents.index(current_agent)
        return agents[(current_idx + 1) % 3]

    def is_terminal_state(self, state):
        """Checks if the game has met any termination conditions[cite: 1]."""
        # Condition 1: Round limit reached (assuming you track state.round)[cite: 1]
        if getattr(state, 'round', 0) >= 30: # Configurable limit, default 30[cite: 1]
            return True
            
        total_cells = state.n * state.m
        obstacle_count = sum(1 for row in state.grid for cell in row if cell.type == 'X')
        valid_cells = total_cells - obstacle_count
        
        active_agents = 0
        for agent_id, agent in state.agents.items():
            # Condition 2: 60% Domination[cite: 1]
            owned_cells = sum(1 for row in state.grid for cell in row if cell.type == agent_id)
            if valid_cells > 0 and (owned_cells / valid_cells) > 0.60:
                return True
                
            # Track if agent is still alive
            if agent.energy > 0 or len(agent.units) > 0:
                active_agents += 1

        # Condition 3: Only one (or zero) agents left with energy/units[cite: 1]
        if active_agents <= 1:
            return True

        return False
    

    def generate_legal_moves(self, state, agent_id):
        """Generates all valid Action combinations for the agent's units."""
        agent = state.agents[agent_id]
        
        # If out of energy, the only legal move is Wait for all units[cite: 1]
        if agent.energy <= 0:
            return [[('Wait', None)] * len(agent.units)]

        unit_actions = []
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)] # 4-directional[cite: 1]

        for unit_idx, pos in enumerate(agent.units):
            # If disabled by a mine, forced to wait[cite: 1]
            if agent.disabled_turns.get(unit_idx, 0) > 0:
                unit_actions.append([('Wait', None)])
                continue

            actions = [('Wait', None)]
            x, y = pos
            
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 <= nx < state.n and 0 <= ny < state.m:
                    target_cell = state.grid[nx][ny]
                    
                    # Cannot interact with Obstacles[cite: 1]
                    if target_cell.type == 'X':
                        continue
                        
                    # Move (Empty, Minefield, or Opponent cell triggering combat)[cite: 1]
                    actions.append(('Move', (nx, ny)))
                    
                    # Attack (Must be opponent-owned)[cite: 1]
                    if target_cell.type in ['A', 'B', 'C'] and target_cell.type != agent_id:
                        actions.append(('Attack', (nx, ny)))
                        
                    # Fortify (Must be currently owned by agent, max defense 3)[cite: 1]
                    if target_cell.type == agent_id and target_cell.defense_value < 3:
                        actions.append(('Fortify', (nx, ny)))

            unit_actions.append(actions)

        # Return the Cartesian product of all units' possible actions
        # E.g., (Unit 1 Moves Up, Unit 2 Attacks Left)
        if not unit_actions:
            return []
        return list(itertools.product(*unit_actions))

    def simulate_move(self, state, move):
        """
        Creates a deepcopy and queues the move. We do NOT resolve combat/mines 
        here because that belongs in the Chance Node.
        """
        new_state = copy.deepcopy(state)
        # Attach the pending move to the state object to be processed next
        new_state.pending_agent = self.agent_id
        new_state.pending_move = move 
        return new_state
    

    def get_chance_outcomes(self, state):
        """
        Takes the queued move and resolves it into branches based on probabilities[cite: 1].
        Returns: list of (probability, new_state) tuples.
        """
        # If no stochastic events are triggered (e.g., both units just Waited or Fortified),
        # return a single 100% probability branch.
        agent = state.agents[state.pending_agent]
        is_stochastic = False
        
        # Check if the queued moves trigger dice rolls (Attacks or Moving into Opponents/Mines)
        for action, target in state.pending_move:
            if action == 'Attack':
                is_stochastic = True
            elif action == 'Move':
                tx, ty = target
                cell_type = state.grid[tx][ty].type
                if cell_type == 'M' or (cell_type in ['A', 'B', 'C'] and cell_type != state.pending_agent):
                    is_stochastic = True

        if not is_stochastic:
            # Apply deterministic effects directly
            self._apply_deterministic_actions(state, state.pending_agent, state.pending_move)
            return [(1.0, state)]

        # --- STOCHASTIC BRANCHING ---
        outcomes = []
        
        # Note: If BOTH units perform stochastic actions, you must calculate the 
        # cross-product of their probabilities (e.g., 9 faces * 9 faces = 81 branches).
        # For brevity in this stub, assuming we generate all valid (prob, state) pairs:
        
        # 1. Generate all possible combinations of outcomes for the pending moves based
        #    on the uneven 9-sided die probabilities or 4-sided mine events[cite: 1].
        # 2. For each combination:
        #      branch_state = copy.deepcopy(state)
        #      apply_specific_outcomes(branch_state)
        #      outcomes.append( (combined_probability, branch_state) )
        
        # (You will need to use the probability tables defined in your GameState here)
        return outcomes
    

    def evaluation_function(self, state, maximizing_agent_id):
        """
        Evaluates the board state. Behavior changes strictly based on agent capability[cite: 1].
        Expert (A): Full 5 factors.
        Intermediate (B): 3 factors.
        Novice (C): Greedy (Score differential only)[cite: 1].
        """
        max_agent = state.agents[maximizing_agent_id]
        opponents = [a for aid, a in state.agents.items() if aid != maximizing_agent_id]
        
        avg_opp_score = sum(o.score for o in opponents) / max(1, len(opponents))
        
        # Factor 1: Score Differential (Used by ALL agents)
        score_diff = max_agent.score - avg_opp_score
        
        # NOVICE AGENT (C) stops here - Greedy evaluation[cite: 1]
        if self.agent_id == 'C':
            return score_diff
            
        # Factor 2: Territory Control (Owned cells + heavily weighted fortresses)[cite: 1]
        territory = 0
        for row in state.grid:
            for cell in row:
                if cell.type == maximizing_agent_id:
                    territory += 1
                    # Highly value Fortresses since they yield +3 points[cite: 1]
                    if getattr(cell, 'is_fortress_base', False): 
                        territory += 3 
                        
        # Factor 3: Energy Advantage[cite: 1]
        avg_opp_energy = sum(o.energy for o in opponents) / max(1, len(opponents))
        energy_adv = max_agent.energy - avg_opp_energy

        # INTERMEDIATE AGENT (B) stops here - 3 Factors[cite: 1]
        if self.agent_id == 'B':
            return (score_diff * 1.5) + (territory * 1.0) + (energy_adv * 0.5)

        # EXPERT AGENT (A) gets the full 5 factors[cite: 1]
        # Factor 4: Positional Advantage (Proximity to high-value cells)[cite: 1]
        # Factor 5: Threat Assessment (Defensive penalty for adjacent opponents)[cite: 1]
        positional_score = self._calculate_proximity_to_fortresses(state, max_agent.units)
        threat_penalty = self._calculate_opponent_threats(state, maximizing_agent_id)

        # Final weighted sum for Expert[cite: 1]
        return (score_diff * 2.0) + (territory * 1.5) + (energy_adv * 0.5) + (positional_score * 0.8) - (threat_penalty * 1.2)
    

    # --- Evaluation Helper Functions (For the Expert Agent) ---

    def _calculate_positional_advantage(self, state, units):
        """Calculates proximity to high-value targets (Fortresses)."""
        score = 0
        fortress_coords = []
        
        # Find all fortresses
        for r in range(state.n):
            for c in range(state.m):
                if getattr(state.grid[r][c], 'is_fortress', False):
                    fortress_coords.append((r, c))
                    
        if not fortress_coords:
            return 0 # No fortresses left
            
        for ux, uy in units:
            # Find the closest fortress using Manhattan Distance
            min_dist = min(abs(ux - fx) + abs(uy - fy) for fx, fy in fortress_coords)
            if min_dist > 0:
                # The closer it is, the higher the score (inverse distance)
                score += 10.0 / min_dist
            else:
                score += 10.0 # Sitting directly on it
                
        return score

    def _calculate_threats(self, state, agent_id):
        """Calculates defensive threats from adjacent opponent units."""
        threat_count = 0
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        
        # Find all opponent units
        opp_units = []
        for aid, a in state.agents.items():
            if aid != agent_id:
                opp_units.extend(a.units)
                
        for ox, oy in opp_units:
            for dx, dy in directions:
                nx, ny = ox + dx, oy + dy
                if 0 <= nx < state.n and 0 <= ny < state.m:
                    # If an opponent unit is adjacent to a cell we own, that's a threat
                    if state.grid[nx][ny].type == agent_id:
                        # Extra penalty if they are threatening a low-defense cell
                        if state.grid[nx][ny].defense_value == 1:
                            threat_count += 2 
                        else:
                            threat_count += 1
                            
        return threat_count
    


class GameGUI:
    def __init__(self, game_state):
        self.state = game_state
        self.cell_size = 50
        self.is_running = False  # For the "Run" button
        
        # Color Dictionary for rendering
        self.colors = {
            '.': (200, 200, 200, 255),  # Empty: Light Grey
            'X': (50, 50, 50, 255),     # Obstacle: Dark Grey
            'F': (255, 215, 0, 255),    # Fortress: Gold
            'M': (255, 69, 0, 255),     # Minefield: Red-Orange
            'A': (65, 105, 225, 255),   # Agent A (Expert): Royal Blue
            'B': (50, 205, 50, 255),    # Agent B (Intermediate): Lime Green
            'C': (147, 112, 219, 255)   # Agent C (Novice): Purple
        }

    def setup_gui(self):
        dpg.create_context()
        dpg.create_viewport(title='Stochastic Battlefield Game', width=1200, height=800)
        dpg.setup_dearpygui()

        with dpg.window(label="Main", width=1200, height=800, no_title_bar=True, no_resize=True):
            with dpg.group(horizontal=True):
                
                # --- LEFT PANEL: THE BOARD GRID ---
                with dpg.child_window(width=600, height=750, border=False):
                    dpg.add_text("Battlefield Map")
                    with dpg.drawlist(width=600, height=600, tag="board_canvas"):
                        pass # We will draw the grid here dynamically

                # --- RIGHT PANEL: LIVE STATS & CONTROLS ---
                with dpg.child_window(width=550, height=750):
                    
                    # 1. Controls[cite: 1]
                    dpg.add_text("Game Controls")
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Next Move", callback=self.step_game, width=120)
                        dpg.add_button(label="Run", callback=self.toggle_run, width=120)
                    dpg.add_separator()

                    # 2. Agent Stats Panel[cite: 1]
                    dpg.add_text("Agent Statistics", color=(255, 215, 0, 255))
                    for agent_id in ['A', 'B', 'C']:
                        with dpg.group(horizontal=True):
                            dpg.add_text(f"Agent {agent_id}: ")
                            dpg.add_text("Score: 0 | Energy: 20 | Units: 2 | Cells: 1", tag=f"stats_{agent_id}")
                    dpg.add_separator()

                    # 3. AI Node Statistics[cite: 1]
                    dpg.add_text("Expectiminimax Per-Move Stats", color=(0, 255, 255, 255))
                    dpg.add_text("Last Action Nodes Explored: 0", tag="nodes_explored")
                    dpg.add_text("Last Action Nodes Pruned: 0 (0.0%)", tag="nodes_pruned")
                    dpg.add_separator()

                    # 4. Move Log Panel[cite: 1]
                    dpg.add_text("Move Log")
                    with dpg.child_window(width=530, height=300, tag="move_log_window"):
                        dpg.add_text("Game Initialized...", tag="move_log_text")

        self.render_board()
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()

    def render_board(self):
        """Draws the grid based on the current GameState."""
        dpg.delete_item("board_canvas", children_only=True)
        
        for r in range(self.state.n):
            for c in range(self.state.m):
                cell = self.state.grid[r][c]
                x1, y1 = c * self.cell_size, r * self.cell_size
                x2, y2 = x1 + self.cell_size, y1 + self.cell_size
                
                # Determine cell base color
                color = self.colors.get(cell.type, self.colors['.'])
                
                # Draw the cell tile
                dpg.draw_rectangle([x1, y1], [x2, y2], color=(0, 0, 0, 255), fill=color, parent="board_canvas")
                
                # Overlay Defense Value if owned or Fortress
                if cell.defense_value > 0:
                    dpg.draw_text([x1 + 15, y1 + 15], str(cell.defense_value), color=(255, 255, 255, 255), size=20, parent="board_canvas")

        # Draw Agent Units (as circles)
        for agent_id, agent in self.state.agents.items():
            for ux, uy in agent.units:
                cx = uy * self.cell_size + (self.cell_size // 2)
                cy = ux * self.cell_size + (self.cell_size // 2)
                # Darker circle to represent the physical unit
                dpg.draw_circle([cx, cy], self.cell_size // 3, fill=(0, 0, 0, 150), parent="board_canvas")

    def update_stats_panel(self, current_agent_id, explored, pruned):
        """Updates the right-side text panels with fresh GameState data[cite: 1]."""
        for aid, agent in self.state.agents.items():
            owned_cells = sum(1 for row in self.state.grid for cell in row if cell.type == aid)
            stat_str = f"Score: {agent.score} | Energy: {agent.energy} | Units: {len(agent.units)} | Cells: {owned_cells}"
            dpg.set_value(f"stats_{aid}", stat_str)

        # Update AI stats
        dpg.set_value("nodes_explored", f"Last Action Nodes Explored: {explored}")
        pruning_eff = (pruned / explored * 100) if explored > 0 else 0
        dpg.set_value("nodes_pruned", f"Last Action Nodes Pruned: {pruned} ({pruning_eff:.1f}%)")

    def log_move(self, text):
        """Appends text to the move log[cite: 1]."""
        current_text = dpg.get_value("move_log_text")
        # Keep log from getting infinitely long
        lines = current_text.split('\n')[-20:] 
        lines.append(text)
        dpg.set_value("move_log_text", '\n'.join(lines))
        # Auto-scroll to bottom
        dpg.set_y_scroll("move_log_window", dpg.get_y_scroll_max("move_log_window"))

    # --- GAME LOOP HOOKS ---

    def step_game(self):
        """Callback for 'Next Move' button. You hook your AI here!"""
        if self.state.is_terminal_state():
            self.log_move("Game Over!")
            self.is_running = False
            return

        # 1. Determine whose turn it is
        # 2. Call your agent's Expectiminimax get_best_move()
        # 3. Execute the move & resolve chance events
        # 4. Gather the stats (explored, pruned) from the AI

        # Example mock update:
        # self.log_move(f"Agent A used Attack on (3,4). Outcome: Full Success")
        # self.update_stats_panel('A', 4821, 1203)
        self.render_board()

    def toggle_run(self):
        """Callback for 'Run' button. Runs game in a background thread."""
        self.is_running = not self.is_running
        if self.is_running:
            dpg.set_item_label("Run", "Stop") # Changes button text
            threading.Thread(target=self._run_loop, daemon=True).start()
        else:
            dpg.set_item_label("Run", "Run")

    def _run_loop(self):
        while self.is_running and not self.state.is_terminal_state():
            self.step_game()
            time.sleep(0.5) # Configurable speed[cite: 1]