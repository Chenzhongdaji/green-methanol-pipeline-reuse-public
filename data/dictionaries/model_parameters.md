# Public model parameter dictionary

`config/model_parameters_v01.csv` is the author-generated configuration
carrier for the public demand-preprocessing, directed-flow, and dynamic
analysis chain. Values are assumptions or model controls, not observations.
The file is versioned and hashed in `data/dataset_registry.csv`.

| Column | Definition | Unit or codes | Missing-value policy | Derivation | Related panel |
| --- | --- | --- | --- | --- | --- |
| parameter | Name of one model control or scenario parameter family. | `sector_activity_10kt`, `conversion_factor`, `adoption_share`, `route_share`, `structural_share`, `supply_scenario`, `flow_scale`, `capacity_relaxation_factor`, `transport_cost_per_km`, `transport_emission_per_km` | Blank forbidden. | Author-defined public model configuration. | Figures 4-5 and model audits |
| sector | Demand sector key. | `A`, `B`, `C`, `D`; blank for global controls. | Blank only for global controls. | Sector mapping retained from the public preprocessing contract. | Figure 4 |
| tier | Supply/adoption tier. | `low`, `mid`, `high`; `0` for global controls. | Blank only for non-tier parameters. | Public scenario-tier configuration. | Figures 4-5 |
| year | Anchor year for time-varying controls. | 2025, 2030, 2060; `0` for non-time-varying controls. | Blank forbidden; `0` denotes global row. | PCHIP anchor or global control. | Figure 4 |
| scenario | Scenario key for composition or supply mapping. | `S1`-`S8`, `low`, `base`, `high`; blank otherwise. | Blank allowed for sector/tier controls. | Scenario definitions are explicit in the model code. | Figures 4-5 |
| value | Numeric value or text mapping for the parameter. | Fraction, factor, 10kt/y, integer, relative cost/emission, or text mapping. | Blank forbidden. | Direct configuration value; no private source dependency. | Figures 4-5 |
| unit | Unit or code interpretation for `value`. | `fraction`, `factor`, `10kt/y`, `integer`, `text`, `relative_cost`, `relative_emission`. | Blank forbidden. | Declared alongside every value to prevent silent unit conversion. | Figures 4-5 |
| notes | Short semantic note and boundary. | Free text. | Blank forbidden. | Author documentation. | Figures 4-5 and audit JSON |
