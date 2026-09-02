class Portfolio:
    def __init__(self, initial_cash: float, transaction_cost_bps: float = 5.0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.holdings = 0.0 # Number of shares
        self.transaction_cost_bps = transaction_cost_bps
        self.cumulative_transaction_costs = 0.0
        
    def get_value(self, current_price: float) -> float:
        return self.cash + (self.holdings * current_price)
        
    def execute_trade(self, action: str, quantity: float, price: float):
        if action == "BUY":
            cost = quantity * price
            tx_fee = cost * (self.transaction_cost_bps / 10000.0)
            if self.cash >= (cost + tx_fee):
                self.cash -= (cost + tx_fee)
                self.holdings += quantity
                self.cumulative_transaction_costs += tx_fee
                return tx_fee
            else:
                # Execute maximum possible quantity instead of failing
                max_cost = self.cash / (1 + self.transaction_cost_bps / 10000.0)
                max_qty = max_cost / price
                if max_qty > 0:
                    tx_fee = (max_qty * price) * (self.transaction_cost_bps / 10000.0)
                    self.cash -= (max_qty * price + tx_fee)
                    self.holdings += max_qty
                    self.cumulative_transaction_costs += tx_fee
                    return tx_fee
                return 0.0
        elif action == "SELL":
            qty_to_sell = min(quantity, self.holdings)
            if qty_to_sell > 0:
                revenue = qty_to_sell * price
                tx_fee = revenue * (self.transaction_cost_bps / 10000.0)
                self.cash += (revenue - tx_fee)
                self.holdings -= qty_to_sell
                self.cumulative_transaction_costs += tx_fee
                return tx_fee
            return 0.0
        return 0.0
