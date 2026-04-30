import random

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
        """Resolves the 9-sided die combat system[cite: 1]."""
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