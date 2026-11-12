from module4.pipeline.labels.surge_labels import assign_scheme_a_splits

def get_scheme_a_splits(df_labeled, horizon_k=3, warm_up_L=5):
    return assign_scheme_a_splits(df_labeled, horizon_k=horizon_k, warm_up_L=warm_up_L)

def get_scheme_b_lodo_folds(df_labeled, attack_segments=(2, 3, 4, 5)):
    folds = []
    valid_df = df_labeled[df_labeled["valid_horizon"]].copy()
    for holdout in attack_segments:
        train_df = valid_df[valid_df["segment_id"] != holdout].copy()
        test_df = valid_df[valid_df["segment_id"] == holdout].copy()
        folds.append((holdout, train_df, test_df))
    return folds
