from iconservice import *

TAG = 'Donation'

class Donation(IconScoreBase):
    # Some basic variables to handle our crowdsale, _ADDR_TOKEN_SCORE should be set to our MySampleToken SCORE during deployment
    _ADDR_WEAK_LIST = 'addr_weak_list'
    _FUNDING_GOAL = 'funding_goal'
    _AMOUNT_RAISED = 'amount_raised'
    _DEAD_LINE = 'dead_line'
    _BALANCES = 'balances'
    _JOINER_LIST = 'joiner_list'
    _FUNDING_GOAL_REACHED = 'funding_goal_reached'
    _DONATION_CLOSED = 'donation_closed'

    # You can monitor these events in the Events tab on the live tracker
    @eventlog(indexed=3)
    def FundTransfer(self, backer: Address, amount: int, is_contribution: bool):
        pass

    @eventlog(indexed=1)
    def GoalReached(self, total_amount_raised: int):
        pass

    def __init__(self, db: IconScoreDatabase) -> None:
        super().__init__(db)

        self._addr_weak_list = ArrayDB(self._ADDR_WEAK_LIST, db, value_type=Address)
        self._funding_goal = VarDB(self._FUNDING_GOAL, db, value_type=int)
        self._amount_raised = VarDB(self._AMOUNT_RAISED, db, value_type=int)
        self._dead_line = VarDB(self._DEAD_LINE, db, value_type=int)
        self._balances = DictDB(self._BALANCES, db, value_type=int)
        self._joiner_list = ArrayDB(self._JOINER_LIST, db, value_type=Address)
        self._funding_goal_reached = VarDB(self._FUNDING_GOAL_REACHED, db, value_type=bool)
        self._donation_closed = VarDB(self._DONATION_CLOSED, db, value_type=bool)

    def on_install(self, fundingGoalInIcx: int, durationInBlocks: int) -> None:
        super().on_install()

        Logger.debug(f'on_install: fundingGoalInIcx={fundingGoalInIcx}', TAG)
        Logger.debug(f'on_install: durationInBlocks={durationInBlocks}', TAG)

        self._addr_weak_list.put(Address.from_string("hx11533df1be962ac27f63728f98ecea9e62bdc8b2")) #weak1 wallet
        self._addr_weak_list.put(Address.from_string("hx6334476e9f2519dd2bfb649840acf7bd6775018e")) #weak2 wallet
        self._addr_weak_list.put(Address.from_string("hxe7309b0f58d2baf512933307a345628f79a07f22")) #weak3 wallet

        self._funding_goal.set(fundingGoalInIcx)
        
        # All SCORE operations must be deterministic according to sandbox policies, so we use block height.
        self._dead_line.set(self.block.height + durationInBlocks)

        self._funding_goal_reached.set(False)
        self._donation_closed.set(False)  # start CrowdSale hereafter

    def on_update(self) -> None:
        super().on_update()

    # Normally we'd decorate the fallback method to handle regular ICX fund transfers.
    @payable
    def fallback(self):
        if self._donation_closed.get():
            self.revert('Donation is closed.')

        amount = self.msg.value
        self._balances[self.msg.sender] = self._balances[self.msg.sender] + amount
        self._amount_raised.set(self._amount_raised.get() + amount)

        if self.msg.sender not in self._joiner_list:
            self._joiner_list.put(self.msg.sender)

    # Logs unique contributors
    @external(readonly=True)
    def total_joiner_count(self) -> int:
        return len(self._joiner_list)

    # Deterministic deadline is set using block height
    def _after_dead_line(self) -> bool:
        Logger.debug(f'after_dead_line: block.height = {self.block.height}', TAG)
        Logger.debug(f'after_dead_line: dead_line()  = {self._dead_line.get()}', TAG)
        return self.block.height >= self._dead_line.get()

    # Our goal is 50ICX, before deadline our donation will continue to run until goal is reached
    @external
    def check_goal_reached(self):
        if self._after_dead_line():
            if self._amount_raised.get() >= self._funding_goal.get():
                self._funding_goal_reached.set(True)
                self.GoalReached(self._amount_raised.get())
                Logger.debug(f'Goal reached!', TAG)
            self._donation_closed.set(True)

    # If goal is reached, we'll payout the ICX collected to the weak people, if not, refund the contributors
    @external
    def safe_withdrawal(self):
        if self._after_dead_line():
            # each contributor can withdraw the amount they contributed if the goal was not reached
            if not self._funding_goal_reached.get():
                amount = self._balances[self.msg.sender]
                self._balances[self.msg.sender] = 0
                if amount > 0:
                    if self.icx.send(self.msg.sender, amount):
                        self.FundTransfer(self.msg.sender, amount, False)
                        Logger.debug(f'FundTransfer({self.msg.sender}, {amount}, False)', TAG)
                    else:
                        self._balances[self.msg.sender] = amount

            if self._funding_goal_reached.get() :
                #send ICX to weak people
                for addr in self._addr_weak_list:
                    if self.icx.send(addr, self._balances[addr]):
                        self.FundTransfer(addr, self._balances[addr], False)
                        Logger.debug(f'FundTransfer({addr},'
                                 f'{self._balances[addr]}, False)', TAG)
                    else:
                        # if the transfer to weak people fails, unlock balance
                        Logger.debug(f'Failed to send to weak people!', TAG)
                        self._funding_goal_reached.set(False)