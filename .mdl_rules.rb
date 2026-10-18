# Custom mdl rules for ATS Showcase
# Disables rules that conflict with project conventions or have acceptable false positives

rule 'MD001' do
  # Header levels should only increment by one level at a time
  # DISABLED: YAML frontmatter causes false positives; accept for .github/instructions/*.md
end

rule 'MD013' do
  # Line length limit
  # Set to 120 instead of default 80 for documentation tables and long descriptions
  params line_length: 120
end

rule 'MD029' do
  # Ordered list item prefix
  # DISABLED: Multiple consecutive ordered lists (e.g., steps 1-4, then "If feedback" section with steps 1-4 again) are intentional
end
