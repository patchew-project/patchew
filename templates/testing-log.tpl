% include('templates/header.tpl', title='Series')

<ul class="nav nav-tabs">
    <li role="presentation"><a href="/series/{{series['message-id']}}">Thread</a></li>
    <li role="presentation" class="active"><a href="#">Testing</a></li>
</ul>
<br>


<h3>
    %if series.get('merged'):
        <span class="label label-primary">Merged</span>
    %elif series['testing-start-time']:
        <span class="label label-warning">Testing</span>
    %elif series['testing-passed']:
        <span class="label label-success">Passed</span>
    %elif series['testing-passed'] == False:
        <span class="label label-danger">Failed</span>
    %else:
        <span class="label label-default">Not started</span>
    %end
</h3>
<br>
%if log:
    <pre>{{log}}</pre>
%end

% include('templates/footer.tpl')
