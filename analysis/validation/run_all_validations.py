from v7_opa_identity_test import run_identity_test
from theta_violation_test import run_theta_test
from scope_consistency_test import run_scope_test
from sl_structure_test import run_sl_structure_test
from silent_signal_impact_test import run_silent_signal_test
from reproducibility_test import run_reproducibility_test

def main():
    run_identity_test()
    run_theta_test()
    run_scope_test()
    run_sl_structure_test()
    run_silent_signal_test()
    run_reproducibility_test()

if __name__ == "__main__":
    main()
